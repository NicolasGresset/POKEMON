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
        segmemnt_t buff;
        packet.extract(buff);
        transition select(buff.bottom) {
            0: skip_segments_stack;
            1: parse_ipv4;
        }
    }

    state parse_ipv4 {
        packet.extract(hdr.ipv4);
        transition select(hdr.ipv4.protocol){
            6 : parse_tcp;
            default: accept;
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
        packet.emit(hdr.ipv4);
        packet.emit(hdr.tcp);
    }
}
