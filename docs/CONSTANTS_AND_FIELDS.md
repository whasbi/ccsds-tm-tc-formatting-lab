# Constants and Fields

## Space Packet

- PVN: Packet Version Number
- Type: 0 for TM/reporting, 1 for TC/requesting
- Secondary Header Flag: 0 in this version
- APID: user-configurable
- Sequence Flags: 3, unsegmented
- Sequence Count: user-configurable
- Packet Data Length: Packet Data Field octets minus 1

## TM RS

- J = 8
- E = 16
- n = 255
- k = 223
- parity = 32
- correction capability = 16 byte-symbol errors
- Interleaving depth I = 5
- GF polynomial = `x^8+x^7+x^2+x+1`
- ASM = `1A CF FC 1D`

## TC Transfer Frame

- Primary header = 5 octets
- TFVN: 2 bits
- Bypass: 1 bit
- Control: 1 bit
- Spare: 2 bits
- SCID: 10 bits numeric
- VCID: 6 bits
- Frame length: 10 bits
- Frame sequence number: 8 bits
- FECF optional = 2 octets
