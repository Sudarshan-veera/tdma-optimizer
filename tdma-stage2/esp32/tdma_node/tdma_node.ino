// TDMA demo node for ESP32 (Arduino core 2.x).  UNTESTED SKELETON - check on your own boards.
// 1. python3 -m tdmaopt.export --nodes 5 --out esp32/tdma_node/schedule.h
// 2. Set MY_ID below (0 = gateway, 1..N-1 = relays), flash each board with a different MY_ID.
// Gateway broadcasts a beacon at the start of each frame; every node syncs its slot clock to it,
// transmits only in its own slots (SLOT_MASK) and forwards packets addressed to it to PARENT[MY_ID].
// On Arduino core 3.x the receive callback signature is (const esp_now_recv_info_t*, const uint8_t*, int).
#include <WiFi.h>
#include <esp_now.h>
#include "schedule.h"

#define MY_ID 1

struct Pkt { uint8_t type; uint8_t src; uint8_t dst; uint16_t seq; };   // type 0 = beacon, 1 = data
static const uint8_t BCAST[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
volatile uint32_t frameStartUs = 0;
volatile bool synced = (MY_ID == 0);
volatile int queued = 0;                       // packets waiting to go to our parent
uint16_t seq = 0, delivered = 0;

void onRecv(const uint8_t *mac, const uint8_t *data, int len) {
  if (len != sizeof(Pkt)) return;
  const Pkt *p = (const Pkt *)data;
  if (p->type == 0) { frameStartUs = micros(); synced = true; return; }
  if (p->dst == MY_ID) {
    if (MY_ID == 0) { delivered++; Serial.printf("gateway got seq %u from %u (total %u)\n", p->seq, p->src, delivered); }
    else queued++;                              // forward on our next slot
  }
}

void sendPkt(uint8_t type, uint8_t dst) {
  Pkt p = {type, MY_ID, dst, seq++};
  esp_now_send(BCAST, (uint8_t *)&p, sizeof(p));
}

void setup() {
  Serial.begin(115200);
  WiFi.mode(WIFI_STA);
  if (esp_now_init() != ESP_OK) { Serial.println("esp_now_init failed"); while (1) delay(1000); }
  esp_now_peer_info_t peer = {};
  memcpy(peer.peer_addr, BCAST, 6);
  peer.channel = 1; peer.encrypt = false;
  esp_now_add_peer(&peer);
  esp_now_register_recv_cb(onRecv);
  if (MY_ID == 0) frameStartUs = micros();
}

void loop() {
  static uint32_t lastGen = 0;
  uint32_t now = micros();
  if (MY_ID == 0) {                                       // gateway: beacon every frame
    if (now - frameStartUs >= (uint32_t)FRAME_SLOTS * SLOT_US) { frameStartUs = now; sendPkt(0, 0xFF); }
    return;
  }
  if (!synced) return;
  if (millis() - lastGen > 2000) { lastGen = millis(); queued++; }     // own sensor reading every 2 s
  uint32_t t = (now - frameStartUs) % ((uint32_t)FRAME_SLOTS * SLOT_US);
  static int lastSlot = -1;
  int slot = t / SLOT_US;
  if (slot != lastSlot) {
    lastSlot = slot;
    if (((SLOT_MASK[MY_ID] >> slot) & 1ULL) && queued > 0) { queued--; sendPkt(1, (uint8_t)PARENT[MY_ID]); }
  }
}
