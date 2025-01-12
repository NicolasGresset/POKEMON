/*************************************************************************
*********************** H E A D E R S  ***********************************
*************************************************************************/

const bit<16> TYPE_IPV4 = 0x800;
const bit<16> TYPE_SOURCEROUTING = 0x8849;

const bit<8> IP_PROTO_PROBE = 0xfd;

typedef bit<9>  egressSpec_t;
typedef bit<48> macAddr_t;
typedef bit<32> ip4Addr_t;

const bit<1> TYPE_SOURCEROUTING_LINK = 0;
const bit<1> TYPE_SOURCEROUTING_SEG = 1;

#define MAX_HOP 8
#define _32MAX_HOP 256

/**
* @brief encapsulation headers to impose intermediate nodes of passage for 
* packets
**/
header segmemnt_t{
    ip4Addr_t target;
    bit<1> type;
    bit<1> bottom;
    bit<6> exp;
}

/**
* @brief Probe header
**/
header probe_t{
    ip4Addr_t origin;
    ip4Addr_t target;
    bit<1> fresh;
    bit<1> hit;
    bit<1> recording;
    bit<1> empty_record;
    bit<4> exp;
}

/**
* @brief Record header for one hop
**/
header record_t{
    ip4Addr_t id;
    bit<1> bottom;
    bit<7> exp;
}

header ethernet_t {
    macAddr_t dstAddr;
    macAddr_t srcAddr;
    bit<16>   etherType;
}

header ipv4_t {
    bit<4>    version;
    bit<4>    ihl;
    bit<6>    dscp;
    bit<2>    ecn;
    bit<16>   totalLen;
    bit<16>   identification;
    bit<3>    flags;
    bit<13>   fragOffset;
    bit<8>    ttl;
    bit<8>    protocol;
    bit<16>   hdrChecksum;
    ip4Addr_t srcAddr;
    ip4Addr_t dstAddr;
}

header tcp_t{
    bit<16> srcPort;
    bit<16> dstPort;
    bit<32> seqNo;
    bit<32> ackNo;
    bit<4>  dataOffset;
    bit<4>  res;
    bit<1>  cwr;
    bit<1>  ece;
    bit<1>  urg;
    bit<1>  ack;
    bit<1>  psh;
    bit<1>  rst;
    bit<1>  syn;
    bit<1>  fin;
    bit<16> window;
    bit<16> checksum;
    bit<16> urgentPtr;
}

struct digest_message_t {
    bit<_32MAX_HOP> records;
    ip4Addr_t origin;
    ip4Addr_t target;
}

struct metadata {
    digest_message_t digest_records;
    ip4Addr_t probe_id;
    ip4Addr_t ipv4_target;
    bit<14> ecmp_hash;
    bit<14> ecmp_group_id;
}

struct headers {
    ethernet_t   ethernet;
    segmemnt_t   sourcerouting;
    segmemnt_t[MAX_HOP] sourcerouting_stack;
    ipv4_t       ipv4;
    probe_t      probe;
    record_t[MAX_HOP] records;
    tcp_t        tcp;
}

