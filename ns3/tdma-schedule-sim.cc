/*
 * tdma-schedule-sim.cc
 *
 * Schedule-driven TDMA simulation on the ns-3 event scheduler.
 *
 * ns-3 has no ready-made TDMA MAC, so this program implements the MAC rule itself
 * (a node may transmit only in its own slot) on top of ns-3 nodes, mobility models
 * (for positions and distances), the discrete-event Simulator and the random
 * number streams. The channel is the same disk model the Brain assumes: two radios
 * hear each other if they are within --range metres.
 *
 * Reception rule, per slot, for every transmission t -> receiver r in range:
 *   - r is transmitting in this slot            -> lost (half duplex)
 *   - another transmitter is also in range of r -> lost (collision at r)
 *       * hidden-terminal collision: the interferer is NOT in range of t
 *       * direct collision:          the interferer is in range of t
 *   - otherwise                                 -> delivered
 *
 * Scenarios: the Brain's schedule, a deliberately bad schedule (Node_03 forced into
 * Node_01's slot), token passing (one node per slot), everyone in one slot, and the
 * mean over many random schedules with the same frame length as the Brain's.
 *
 * Input: sim/schedule_sim.csv  (python sim/export_for_sims.py schedule.json sim/schedule_sim.csv)
 *
 * Run (from the ns-3 folder, after copying this file into scratch/):
 *   ./ns3 run "tdma-schedule-sim --input=/home/susan/tdma-optimizer/sim/schedule_sim.csv"
 */

#include "ns3/core-module.h"
#include "ns3/mobility-module.h"
#include "ns3/network-module.h"

#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("TdmaScheduleSim");

struct Topology
{
    std::vector<std::string> names;
    std::vector<Vector> pos;
    std::vector<int> slots; // the Brain's schedule
};

struct Counters
{
    uint64_t attempted = 0;  // (transmitter, in-range receiver) pairs
    uint64_t success = 0;    // delivered
    uint64_t collided = 0;   // lost to a collision at the receiver
    uint64_t hidden = 0;     //   ... of which hidden-terminal collisions
    uint64_t direct = 0;     //   ... of which direct (distance-1) collisions
    uint64_t halfDuplex = 0; // receiver was itself transmitting

    void Add(const Counters& o)
    {
        attempted += o.attempted;
        success += o.success;
        collided += o.collided;
        hidden += o.hidden;
        direct += o.direct;
        halfDuplex += o.halfDuplex;
    }
};

struct Result
{
    std::string name;
    uint32_t slotsPerFrame = 0;
    uint32_t frames = 0;
    Counters c; // totals over all frames
};

/** One scenario: nodes, positions, a slot per node, run for a number of frames. */
class TdmaSim
{
  public:
    TdmaSim(const Topology& topo,
            const std::vector<int>& slots,
            uint32_t slotsPerFrame,
            double range,
            Time slotDur,
            std::ostream* trace)
        : m_slots(slots),
          m_S(slotsPerFrame),
          m_slotDur(slotDur),
          m_trace(trace)
    {
        const uint32_t n = static_cast<uint32_t>(topo.pos.size());
        m_nodes.Create(n);
        Ptr<ListPositionAllocator> alloc = CreateObject<ListPositionAllocator>();
        for (const auto& p : topo.pos)
        {
            alloc->Add(p);
        }
        MobilityHelper mob;
        mob.SetPositionAllocator(alloc);
        mob.SetMobilityModel("ns3::ConstantPositionMobilityModel");
        mob.Install(m_nodes);

        // Neighbour matrix from the ns-3 mobility models (inclusive range, like the Brain).
        m_neigh.assign(n, std::vector<bool>(n, false));
        for (uint32_t i = 0; i < n; ++i)
        {
            Ptr<MobilityModel> mi = m_nodes.Get(i)->GetObject<MobilityModel>();
            for (uint32_t j = 0; j < n; ++j)
            {
                if (i == j)
                {
                    continue;
                }
                Ptr<MobilityModel> mj = m_nodes.Get(j)->GetObject<MobilityModel>();
                m_neigh[i][j] = mi->GetDistanceFrom(mj) <= range + 1e-9;
            }
        }
        m_names = topo.names;
    }

    Result Run(const std::string& label, uint32_t frames)
    {
        for (uint32_t f = 0; f < frames; ++f)
        {
            for (uint32_t s = 0; s < m_S; ++s)
            {
                Time t = (f * m_S + s) * m_slotDur;
                Simulator::Schedule(t, &TdmaSim::RunSlot, this, f, s);
            }
        }
        Simulator::Run();
        Simulator::Destroy();
        Result r;
        r.name = label;
        r.slotsPerFrame = m_S;
        r.frames = frames;
        r.c = m_c;
        return r;
    }

  private:
    void RunSlot(uint32_t frame, uint32_t slot)
    {
        const uint32_t n = static_cast<uint32_t>(m_slots.size());
        std::vector<uint32_t> tx;
        for (uint32_t i = 0; i < n; ++i)
        {
            if (m_slots[i] == static_cast<int>(slot))
            {
                tx.push_back(i);
            }
        }
        uint64_t okHere = 0;
        uint64_t badHere = 0;
        for (uint32_t t : tx)
        {
            for (uint32_t r = 0; r < n; ++r)
            {
                if (!m_neigh[t][r])
                {
                    continue;
                }
                m_c.attempted++;
                if (m_slots[r] == static_cast<int>(slot))
                {
                    m_c.halfDuplex++;
                    badHere++;
                    continue;
                }
                bool collided = false;
                bool hidden = false;
                for (uint32_t u : tx)
                {
                    if (u == t || !m_neigh[u][r])
                    {
                        continue;
                    }
                    collided = true;
                    if (!m_neigh[t][u])
                    {
                        hidden = true; // interferer cannot be heard by t: classic hidden terminal
                    }
                }
                if (collided)
                {
                    m_c.collided++;
                    badHere++;
                    if (hidden)
                    {
                        m_c.hidden++;
                    }
                    else
                    {
                        m_c.direct++;
                    }
                }
                else
                {
                    m_c.success++;
                    okHere++;
                }
            }
        }
        if (m_trace != nullptr && !tx.empty())
        {
            std::ostringstream who;
            for (size_t k = 0; k < tx.size(); ++k)
            {
                who << (k ? "+" : "") << m_names[tx[k]];
            }
            *m_trace << std::fixed << std::setprecision(3) << Simulator::Now().GetMilliSeconds()
                     << "," << frame << "," << slot << "," << who.str() << "," << okHere << ","
                     << badHere << "\n";
        }
    }

    NodeContainer m_nodes;
    std::vector<std::vector<bool>> m_neigh;
    std::vector<std::string> m_names;
    std::vector<int> m_slots;
    uint32_t m_S;
    Time m_slotDur;
    std::ostream* m_trace;
    Counters m_c;
};

static bool
LoadTopology(const std::string& path, Topology& topo)
{
    std::ifstream in(path);
    if (!in)
    {
        return false;
    }
    std::string line;
    while (std::getline(in, line))
    {
        if (!line.empty() && line.back() == '\r')
        {
            line.pop_back();
        }
        if (line.empty() || line[0] == '#')
        {
            continue;
        }
        std::vector<std::string> f;
        std::stringstream ss(line);
        std::string tok;
        while (std::getline(ss, tok, ','))
        {
            f.push_back(tok);
        }
        if (f.size() < 4 || f[0] == "name")
        {
            continue;
        }
        topo.names.push_back(f[0]);
        topo.pos.push_back(Vector(std::stod(f[1]), std::stod(f[2]), 0.0));
        topo.slots.push_back(std::stoi(f[3]));
    }
    return !topo.names.empty();
}

static int
IndexOf(const Topology& t, const std::string& name)
{
    for (size_t i = 0; i < t.names.size(); ++i)
    {
        if (t.names[i] == name)
        {
            return static_cast<int>(i);
        }
    }
    return -1;
}

int
main(int argc, char* argv[])
{
    std::string input = "schedule_sim.csv";
    std::string outCsv = "ns3_results.csv";
    std::string traceFile = "";
    double range = 500.0;
    uint32_t frames = 1000;
    uint32_t slotMs = 1;
    uint32_t randomRuns = 200;
    uint32_t seed = 1;

    CommandLine cmd(__FILE__);
    cmd.AddValue("input", "CSV from sim/export_for_sims.py (name,x,y,slot)", input);
    cmd.AddValue("out", "results CSV to write", outCsv);
    cmd.AddValue("trace", "optional per-slot trace CSV for the Brain schedule", traceFile);
    cmd.AddValue("range", "radio range in metres", range);
    cmd.AddValue("frames", "frames to simulate per scenario", frames);
    cmd.AddValue("slotMs", "slot duration in ms", slotMs);
    cmd.AddValue("randomRuns", "random schedules to average", randomRuns);
    cmd.AddValue("seed", "random seed", seed);
    cmd.Parse(argc, argv);

    Topology topo;
    if (!LoadTopology(input, topo))
    {
        std::cerr << "Cannot read topology from " << input
                  << "\nCreate it with: python sim/export_for_sims.py schedule.json sim/schedule_sim.csv\n";
        return 1;
    }
    const uint32_t n = static_cast<uint32_t>(topo.names.size());
    const uint32_t S = static_cast<uint32_t>(*std::max_element(topo.slots.begin(), topo.slots.end())) + 1;
    const Time slotDur = MilliSeconds(slotMs);
    SeedManager::SetSeed(seed);
    SeedManager::SetRun(1);

    std::cout << "ns-3 TDMA schedule simulation\n"
              << "  radios: " << n << ", range: " << range << " m, Brain frame length: " << S
              << " slots, slot: " << slotMs << " ms, frames: " << frames << "\n\n";

    std::vector<Result> results;

    // 1. The Brain's schedule (optionally with a per-slot trace)
    {
        std::unique_ptr<std::ofstream> tr;
        if (!traceFile.empty())
        {
            tr.reset(new std::ofstream(traceFile));
            *tr << "time_ms,frame,slot,transmitters,delivered,lost\n";
        }
        TdmaSim sim(topo, topo.slots, S, range, slotDur, tr.get());
        results.push_back(sim.Run("Brain schedule", frames));
    }

    // 2. Bad schedule: Node_03 forced into Node_01's slot (hidden terminals around Node_02)
    {
        std::vector<int> bad = topo.slots;
        int a = IndexOf(topo, "Node_01");
        int b = IndexOf(topo, "Node_03");
        if (a >= 0 && b >= 0)
        {
            bad[b] = bad[a];
            TdmaSim sim(topo, bad, S, range, slotDur, nullptr);
            results.push_back(sim.Run("Bad: Node_03 in Node_01's slot", frames));
        }
    }

    // 3. Token passing: one node per slot
    {
        std::vector<int> tok(n);
        for (uint32_t i = 0; i < n; ++i)
        {
            tok[i] = static_cast<int>(i);
        }
        TdmaSim sim(topo, tok, n, range, slotDur, nullptr);
        results.push_back(sim.Run("Token passing (1 node per slot)", frames));
    }

    // 4. Everyone in one slot
    {
        std::vector<int> one(n, 0);
        TdmaSim sim(topo, one, 1, range, slotDur, nullptr);
        results.push_back(sim.Run("All nodes in one slot", frames));
    }

    // 5. Random schedules with the same frame length as the Brain's (one frame each is
    //    enough: the schedule repeats every frame, so per-frame results do not change)
    {
        Ptr<UniformRandomVariable> rv = CreateObject<UniformRandomVariable>();
        Counters total;
        for (uint32_t k = 0; k < randomRuns; ++k)
        {
            std::vector<int> rnd(n);
            for (uint32_t i = 0; i < n; ++i)
            {
                rnd[i] = static_cast<int>(rv->GetInteger(0, S - 1));
            }
            TdmaSim sim(topo, rnd, S, range, slotDur, nullptr);
            total.Add(sim.Run("random", 1).c);
        }
        Result r;
        r.name = "Random schedule (mean of " + std::to_string(randomRuns) + ")";
        r.slotsPerFrame = S;
        r.frames = randomRuns; // one frame per random schedule
        r.c = total;
        results.push_back(r);
    }

    // Report
    std::ofstream csv(outCsv);
    csv << "scenario,slots_per_frame,frames,attempted_per_frame,delivered_per_frame,"
           "collisions_per_frame,hidden_terminal_per_frame,direct_per_frame,half_duplex_per_frame,"
           "delivery_ratio,delivered_per_second\n";
    std::cout << std::left << std::setw(36) << "Scenario" << std::right << std::setw(7) << "Slots"
              << std::setw(11) << "Delivered" << std::setw(11) << "Collided" << std::setw(9)
              << "Hidden" << std::setw(9) << "Direct" << std::setw(11) << "Delivery" << std::setw(14)
              << "Deliv./sec\n";
    std::cout << std::string(108, '-') << "\n";
    for (const auto& r : results)
    {
        const double f = static_cast<double>(r.frames);
        const double att = r.c.attempted / f;
        const double ok = r.c.success / f;
        const double col = r.c.collided / f;
        const double hid = r.c.hidden / f;
        const double dir = r.c.direct / f;
        const double hd = r.c.halfDuplex / f;
        const double ratio = r.c.attempted ? static_cast<double>(r.c.success) / r.c.attempted : 0.0;
        const double frameSec = r.slotsPerFrame * slotMs / 1000.0;
        const double perSec = ok / frameSec;
        std::cout << std::left << std::setw(36) << r.name << std::right << std::setw(7)
                  << r.slotsPerFrame << std::fixed << std::setprecision(2) << std::setw(11) << ok
                  << std::setw(11) << col << std::setw(9) << hid << std::setw(9) << dir
                  << std::setw(10) << ratio * 100.0 << "%" << std::setprecision(0) << std::setw(14)
                  << perSec << "\n";
        csv << "\"" << r.name << "\"," << r.slotsPerFrame << "," << r.frames << "," << att << ","
            << ok << "," << col << "," << hid << "," << dir << "," << hd << "," << ratio << ","
            << perSec << "\n";
    }
    std::cout << "\n(per-frame figures; 'Delivered' counts transmitter-to-neighbour receptions)\n";

    const bool pass = results[0].c.collided == 0 && results[0].c.halfDuplex == 0;
    std::cout << "\nBrain schedule check: " << (pass ? "PASS - zero collisions" : "FAIL - collisions found")
              << "\nResults written to " << outCsv << "\n";
    return pass ? 0 : 2;
}
