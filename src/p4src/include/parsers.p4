/*************************************************************************
*********************** P A R S E R  *******************************
*************************************************************************/

parser MyParser(packet_in packet,
                out headers hdr,
                inout metadata meta,
                inout standard_metadata_t standard_metadata) {

    state start {

        transition parse_ethernet;

    }

    state parse_ethernet {

        packet.extract(hdr.ethernet);
        transition select(hdr.ethernet.etherType){
            TYPE_IPV4: parse_ipv4;
            TYPE_SOURCEROUTING: parse_sourcerouting;
            default: accept;
        }
    }

    state parse_sourcerouting{
        packet.extract(hdr.sourcerouting);
        transition select(hdr.sourcerouting.bottom){
            0: skip_segments_stack;
            1: parse_ipv4;
        }
    }

    // Skip the segments stack to reach upper layer informations to 
    // compute ECMP hash.
    state skip_segments_stack{
        packet.extract(hdr.sourcerouting_stack.next);
        transition select(hdr.sourcerouting_stack.last.bottom) {
            0: skip_segments_stack;
            1: parse_ipv4;
        }
    }

    state parse_ipv4 {
        packet.extract(hdr.ipv4);
        transition select(hdr.ipv4.protocol){
            6 : parse_tcp;
            IP_PROTO_PROBE: parse_probe;
            default: accept;
        }
    }

    state parse_probe {
        packet.extract(hdr.probe);
        transition select(hdr.probe.recording, hdr.probe.empty_record) {
            (0, 0): accept;
            (0, 1): accept;
            (1, 0): parse_record;
            (1, 1): accept;
        }
    }

    state parse_record{
        packet.extract(hdr.records.next);
        transition select(hdr.records.last.bottom){
            0: parse_record;
            1: accept;
        }
    }

    state parse_tcp {
        packet.extract(hdr.tcp);
        transition accept;
    }
}

/*************************************************************************
***********************  D E P A R S E R  *******************************
*************************************************************************/

control MyDeparser(packet_out packet, in headers hdr) {
    apply {

        //parsed headers have to be added again into the packet.
        packet.emit(hdr.ethernet);
        packet.emit(hdr.sourcerouting);
        packet.emit(hdr.sourcerouting_stack);
        packet.emit(hdr.ipv4);
        packet.emit(hdr.probe);
        packet.emit(hdr.records);
        packet.emit(hdr.tcp);
    }
}
