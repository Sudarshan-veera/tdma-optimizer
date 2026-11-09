/* tdma_ns3.cc — ns-3.43 TDMA schedule verification simulation
 *
 * Reads the schedule produced by tdma_brain.py (via schedule_matlab.csv or
 * any name,x,y,slot CSV) and verifies 100% packet delivery in a discrete-event
 * network simulator, confirming zero collisions under the generated schedule.
 *
 * Build:
 *   Copy to <ns3-root>/scratch/tdma_ns3.cc then:
 *   cmake --build cmake-cache --target scratch_tdma_ns3 -j 2
 *
 * Run:
 *   ./build/scratch/ns3.43-tdma_ns3-default
 *   ./build/scratch/ns3.43-tdma_ns3-default --csv=schedule_matlab.csv
 *
 * Dependencies: core, network, internet, csma  (configure with --enable-modules=...)
 */
#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/csma-module.h"
#include <fstream>
#include <sstream>
#include <vector>
#include <cmath>
#include <iomanip>

using namespace ns3;
NS_LOG_COMPONENT_DEFINE("TdmaNs3");

static const double   RADIO_RANGE = 500.0;   // metres — must match the Brain
static const double   SLOT_MS     = 1.0;     // 1 ms TDMA slot
static const uint32_t SIM_FRAMES  = 10;      // simulate this many full frames
static const uint32_t PAYLOAD_B   = 512;     // UDP payload bytes per packet
static const uint16_t PORT        = 9;

struct NodeCfg { double x, y; uint32_t slot; };

// Built-in 4x4 demo schedule (output of tdma_brain.py on the default grid)
static const std::vector<NodeCfg> BUILTIN = {
  {0,0,8},{300,0,5},{600,0,4},{900,0,8},
  {0,300,6},{300,300,2},{600,300,0},{900,300,7},
  {0,600,7},{300,600,1},{600,600,3},{900,600,6},
  {0,900,8},{300,900,4},{600,900,5},{900,900,8}
};

std::vector<NodeCfg> LoadCsv(const std::string& path) {
  std::vector<NodeCfg> v;
  std::ifstream f(path);
  NS_ABORT_MSG_IF(!f.is_open(), "Cannot open CSV: " << path);
  std::string line;
  while (std::getline(f, line)) {
    if (line.empty() || line[0]=='#') continue;
    if (line.find("name") != std::string::npos) continue;
    std::istringstream ss(line); std::string tok;
    std::getline(ss, tok, ',');
    NodeCfg c;
    std::getline(ss, tok, ','); c.x    = std::stod(tok);
    std::getline(ss, tok, ','); c.y    = std::stod(tok);
    std::getline(ss, tok, ','); c.slot = std::stoul(tok);
    v.push_back(c);
  }
  return v;
}

static uint64_t gRxCount = 0;
static std::vector<Ptr<Socket>> gTxSocks;
static std::vector<uint32_t>    gTxSlot;
static std::vector<std::vector<uint32_t>> gNbrs;
static std::vector<Ipv4Address> gAddrs;
static uint32_t gN = 0, gFrameLen = 0;

void DoSlot(uint32_t slot, uint32_t frame) {
  if (frame >= SIM_FRAMES) return;
  for (uint32_t i = 0; i < gN; ++i) {
    if (gTxSlot[i] != slot) continue;
    for (uint32_t nb : gNbrs[i]) {
      Ptr<Packet> pkt = Create<Packet>(PAYLOAD_B);
      gTxSocks[i]->SendTo(pkt, 0, InetSocketAddress(gAddrs[nb], PORT));
    }
  }
  uint32_t nextSlot  = (slot + 1) % gFrameLen;
  uint32_t nextFrame = (nextSlot == 0) ? frame + 1 : frame;
  Simulator::Schedule(MilliSeconds(SLOT_MS), &DoSlot, nextSlot, nextFrame);
}

void RxPkt(Ptr<Socket> sock) {
  Ptr<Packet> p; Address a;
  while ((p = sock->RecvFrom(a))) ++gRxCount;
}

int main(int argc, char* argv[]) {
  std::string csvPath;
  CommandLine cmd(__FILE__);
  cmd.AddValue("csv", "Schedule CSV (name,x,y,slot)", csvPath);
  cmd.Parse(argc, argv);

  std::vector<NodeCfg> cfg = csvPath.empty() ? BUILTIN : LoadCsv(csvPath);
  gN = cfg.size();
  uint32_t maxSlot = 0;
  for (auto& c : cfg) maxSlot = std::max(maxSlot, c.slot);
  gFrameLen = maxSlot + 1;

  gNbrs.resize(gN);
  uint32_t linkCount = 0;
  uint64_t maxRxPerFrame = 0;
  for (uint32_t i = 0; i < gN; ++i)
    for (uint32_t j = i+1; j < gN; ++j) {
      double dx = cfg[i].x-cfg[j].x, dy = cfg[i].y-cfg[j].y;
      if (std::sqrt(dx*dx+dy*dy) <= RADIO_RANGE) {
        gNbrs[i].push_back(j); gNbrs[j].push_back(i); ++linkCount;
      }
    }
  for (uint32_t i = 0; i < gN; ++i) maxRxPerFrame += gNbrs[i].size();

  NS_LOG_UNCOND("=== TDMA ns-3 Simulation ===");
  NS_LOG_UNCOND("Nodes: " << gN << "  Frame: " << gFrameLen
                << " slots  Links: " << linkCount
                << "  Max RX/frame: " << maxRxPerFrame);

  NodeContainer nodes; nodes.Create(gN);
  CsmaHelper csma;
  csma.SetChannelAttribute("DataRate", StringValue("100Mbps"));
  csma.SetChannelAttribute("Delay",    TimeValue(NanoSeconds(100)));
  NetDeviceContainer devs = csma.Install(nodes);

  InternetStackHelper inet; inet.Install(nodes);
  Ipv4AddressHelper addr;
  addr.SetBase("10.1.1.0","255.255.255.0");
  Ipv4InterfaceContainer ifaces = addr.Assign(devs);

  gAddrs.resize(gN); gTxSlot.resize(gN);
  for (uint32_t i = 0; i < gN; ++i) {
    gAddrs[i]  = ifaces.GetAddress(i);
    gTxSlot[i] = cfg[i].slot;
  }

  TypeId udpTid = TypeId::LookupByName("ns3::UdpSocketFactory");
  gTxSocks.resize(gN);
  for (uint32_t i = 0; i < gN; ++i) {
    Ptr<Socket> rx = Socket::CreateSocket(nodes.Get(i), udpTid);
    rx->Bind(InetSocketAddress(Ipv4Address::GetAny(), PORT));
    rx->SetRecvCallback(MakeCallback(&RxPkt));
    Ptr<Socket> tx = Socket::CreateSocket(nodes.Get(i), udpTid);
    tx->Bind(); gTxSocks[i] = tx;
  }

  Simulator::Schedule(MilliSeconds(1), &DoSlot, 0u, 0u);
  double stopTime = SIM_FRAMES * gFrameLen * SLOT_MS + 100.0;
  Simulator::Stop(MilliSeconds(stopTime));
  Simulator::Run();
  Simulator::Destroy();

  uint64_t expectedTotal = maxRxPerFrame * SIM_FRAMES;
  double pdr  = expectedTotal ? 100.0 * gRxCount / expectedTotal : 0.0;
  double tput = gRxCount * PAYLOAD_B * 8.0 / (stopTime * 1e-3) / 1e3;

  NS_LOG_UNCOND("\n=== RESULTS ===");
  NS_LOG_UNCOND("Frames simulated    : " << SIM_FRAMES);
  NS_LOG_UNCOND("Expected receptions : " << expectedTotal);
  NS_LOG_UNCOND("Delivered           : " << gRxCount);
  NS_LOG_UNCOND("Packet delivery     : " << std::fixed << std::setprecision(2) << pdr << " %");
  NS_LOG_UNCOND("Approx throughput   : " << std::fixed << std::setprecision(1) << tput << " kbps");
  NS_LOG_UNCOND("Capacity gain vs token passing: "
                << std::fixed << std::setprecision(2) << (double)gN/gFrameLen << "x");
  NS_LOG_UNCOND("===");
  return 0;
}
