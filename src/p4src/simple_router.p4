/* -*- P4_16 -*- */
#include <core.p4>
#include <v1model.p4>

//My includes
#include "include/headers.p4"
#include "include/parsers.p4"

/*************************************************************************
************   C H E C K S U M    V E R I F I C A T I O N   *************
*************************************************************************/

control MyVerifyChecksum(inout headers hdr, inout metadata meta) {
    apply {  }
}

/*************************************************************************
**************  I N G R E S S   P R O C E S S I N G   *******************
*************************************************************************/

control MyIngress(inout headers hdr,
                  inout metadata meta,
                  inout standard_metadata_t standard_metadata) {
    register<ip4Addr_t>(1) probe_id;

    action drop() {
        mark_to_drop(standard_metadata);
    }

    action ecmp_group(bit<14> ecmp_group_id, bit<16> num_nhops){
        hash(meta.ecmp_hash,
	    HashAlgorithm.crc16,
	    (bit<1>)0,
	    { hdr.ipv4.srcAddr,
	      hdr.ipv4.dstAddr,
          hdr.tcp.srcPort,
          hdr.tcp.dstPort,
          hdr.ipv4.protocol},
	    num_nhops);

	    meta.ecmp_group_id = ecmp_group_id;
    }

    action set_nhop(macAddr_t dstAddr, egressSpec_t port) {

        //set the src mac address as the previous dst, this is not correct right?
        hdr.ethernet.srcAddr = hdr.ethernet.dstAddr;

       //set the destination mac address that we got from the match in the table
        hdr.ethernet.dstAddr = dstAddr;

        //set the output port that we also get from the table
        standard_metadata.egress_spec = port;

        //decrease ttl by 1
        hdr.ipv4.ttl = hdr.ipv4.ttl - 1;
    }
    
    action pop_segment() {
        # Update etherType when last segment is pop
        if(hdr.sourcerouting.bottom == 1){
            hdr.ethernet.etherType = TYPE_IPV4;
        }

        hdr.sourcerouting.setInvalid();
    }

    action record() {
        hdr.records.push_front(1);
        hdr.records[MAX_HOP - 1].bottom = 1;


        hdr.records[0].setValid();
        hdr.records[0].id = meta.probe_id;
        if(hdr.probe.empty_record == 1) {
            hdr.probe.empty_record = 0;
            hdr.records[0].bottom = 1;
        }
        else
            hdr.records[0].bottom = 0;
    }

    action copy_to_digest() {
        meta.digest_records = ((bit<_32MAX_HOP>)hdr.records[0].id) << 32 * 0; 
        meta.digest_records = ((bit<_32MAX_HOP>)hdr.records[1].id) << 32 * 1;
        meta.digest_records = ((bit<_32MAX_HOP>)hdr.records[2].id) << 32 * 2;
        meta.digest_records = ((bit<_32MAX_HOP>)hdr.records[3].id) << 32 * 3;
        meta.digest_records = ((bit<_32MAX_HOP>)hdr.records[4].id) << 32 * 4;
        meta.digest_records = ((bit<_32MAX_HOP>)hdr.records[5].id) << 32 * 5;
        meta.digest_records = ((bit<_32MAX_HOP>)hdr.records[6].id) << 32 * 6;
        meta.digest_records = ((bit<_32MAX_HOP>)hdr.records[7].id) << 32 * 7;
    }


#ifdef LOSSY_ROUTER
    action lossy_logic(){
        bit<32> random_value;
        random(random_value, (bit<32>)1, (bit<32>)100);
        if (random_value <= 30){
            standard_metadata.egress_spec = DROP_PORT;
        }
    }
#endif

#ifdef STUPID_ROUTER
    register<bit<8>>(1) number_of_ports;

    action stupid_logic(){
        bit<8> number_of_port;
        bit<32> random_port;

        number_of_ports.read(number_of_port, (bit<32>) 0);
        random(random_port, (bit<32>)1, (bit<32>)number_of_port);

        standard_metadata.egress_spec = (bit<9>)(random_port);
    }
#endif

    table ecmp_group_to_nhop {
        key = {
            meta.ecmp_group_id:    exact;
            meta.ecmp_hash: exact;
        }
        actions = {
            drop;
            set_nhop;
        }
        size = 1024;
    }

    table ipv4_lpm {
        key = {
            meta.ipv4_target: lpm;
        }
        actions = {
            set_nhop;
            ecmp_group;
            drop;
        }
        size = 1024;
        default_action = drop;
    }

    table sourcerouting_link {
        key = {
            hdr.sourcerouting.target: lpm;
        }
        actions = {
            set_nhop;
            drop;
        }
        size = 64;
        default_action = drop;
    }

    table sourcerouting_penultimate_hop {
        key = {
            hdr.sourcerouting.target: lpm;
        }
        actions = {
            pop_segment;
            NoAction;
        }
        size = 64;
        default_action = NoAction;
    }

    direct_counter(CounterType.packets) outgoing_probes;
    direct_counter(CounterType.packets) incoming_probes;
    
    table count_outgoing_probes{
        key = {
            hdr.probe.target: exact;
        }
        actions = {
            NoAction;
        }
        size = 64;
        counters = outgoing_probes;
        default_action = NoAction;
    }

    table count_incoming_probes{
        key = {
            hdr.probe.target: exact;
        }
        actions = {
            NoAction;
        }
        size = 64;
        counters = incoming_probes;
        default_action = NoAction;
    }

    register<bit<32>>(1) register_debug;
    apply {
        meta.ipv4_target = 0;
        if(hdr.sourcerouting.isValid()){
            register_debug.write(0, hdr.sourcerouting.target);
            if (hdr.sourcerouting.type == TYPE_SOURCEROUTING_LINK){
                    sourcerouting_link.apply();
                    pop_segment();
            }
            else if (hdr.sourcerouting.type == TYPE_SOURCEROUTING_SEG){
                    meta.ipv4_target = hdr.sourcerouting.target;
                    sourcerouting_penultimate_hop.apply();
            }
        }
        else if (hdr.ipv4.isValid()){
            meta.ipv4_target = hdr.ipv4.dstAddr;
        }
        if(meta.ipv4_target != 0) {
            switch (ipv4_lpm.apply().action_run){
                ecmp_group: {
                    ecmp_group_to_nhop.apply();
                }
            }

#ifdef STUPID_ROUTER
            stupid_logic();
#endif
        } 

        if(hdr.probe.isValid()){
            probe_id.read(meta.probe_id, 0);

            if(meta.probe_id == hdr.probe.origin) {
                if(hdr.probe.fresh == 1){
                    hdr.probe.fresh = 0;
                    count_outgoing_probes.apply();
                }
                else {
                    count_incoming_probes.apply();
                    if(hdr.probe.recording == 1)
                        copy_to_digest();
                        digest(1, meta.digest_records);
                }
            }
            if(meta.probe_id == hdr.probe.target)
                hdr.probe.hit = 1;

            if(hdr.probe.recording == 1)
                record();
        }

#ifdef LOSSY_ROUTER
        lossy_logic();
#endif
    }
}

/*************************************************************************
****************  E G R E S S   P R O C E S S I N G   *******************
*************************************************************************/

control MyEgress(inout headers hdr,
                 inout metadata meta,
                 inout standard_metadata_t standard_metadata) {
    apply {

    }
}

/*************************************************************************
*************   C H E C K S U M    C O M P U T A T I O N   **************
*************************************************************************/

control MyComputeChecksum(inout headers hdr, inout metadata meta) {
     apply {
	update_checksum(
	    hdr.ipv4.isValid(),
            { hdr.ipv4.version,
	          hdr.ipv4.ihl,
              hdr.ipv4.dscp,
              hdr.ipv4.ecn,
              hdr.ipv4.totalLen,
              hdr.ipv4.identification,
              hdr.ipv4.flags,
              hdr.ipv4.fragOffset,
              hdr.ipv4.ttl,
              hdr.ipv4.protocol,
              hdr.ipv4.srcAddr,
              hdr.ipv4.dstAddr },
              hdr.ipv4.hdrChecksum,
              HashAlgorithm.csum16);
    }
}

/*************************************************************************
***********************  S W I T C H  *******************************
*************************************************************************/

//switch architecture
V1Switch(
MyParser(),
MyVerifyChecksum(),
MyIngress(),
MyEgress(),
MyComputeChecksum(),
MyDeparser()
) main;
