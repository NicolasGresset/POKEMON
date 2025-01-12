from scapy.all import Packet, BitField, IPField

TYPE_SOURCEROUTING = 0x8849;
IP_PROTO_PROBE = 0xfd;

TYPE_SOURCEROUTING_LINK = 0;
TYPE_SOURCEROUTING_SEG = 1;

class ProbeHeader(Packet):
    name = "ProbeHeader"
    fields_desc = [
        IPField("origin", "0.0.0.0"),  # origin as IPv4
        IPField("target", "0.0.0.0"),  # target as IPv4
        BitField("fresh", 0, 1),  # fresh as a 1-bit field
        BitField("hit", 0, 1),  # hit as a 1-bit field
        BitField("recording", 0, 1),  # recording as a 1-bit field
        BitField("empty_record", 1, 1),  # empty_record as a 1-bit field
        BitField("exp", 0, 4),  # experimental as a 4-bit field
    ]


class SegmentHeader(Packet):
    name = "SegmentHeader"
    fields_desc = [
        IPField("target", "0.0.0.0"),  # IPv4 address field
        BitField("type", TYPE_SOURCEROUTING_SEG, 1),  # 1-bit field for 'type'
        BitField("bottom", 0, 1),  # 1-bit field for 'bottom'
        BitField("exp", 0, 6),  # 6-bit field for 'exp'
    ]

    # Define the behavior to guess the next layer
    def guess_payload_class(self, payload):
        # If 'bottom' bit is set, there is no more header to parse
        if self.bottom == 1:
            return Raw  # No more headers, treat remaining as Raw data
        return SegmentHeader  # Otherwise, parse the next header as SegmentHeader
