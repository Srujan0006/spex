// Area probe: one configuration table of N entries x W bits in flops, written by the host port, with P independent
// read ports (address in, data out). Not a design. probe_tables.py synthesises it per table and per port count.
`default_nettype none
module table_ports #(
    parameter N = 16,
    parameter W = 34,
    parameter P = 1
) (
    input  wire clk,
    input  wire we,
    input  wire [$clog2(N)-1:0] waddr,
    input  wire [W-1:0] wdata,
    input  wire [P*$clog2(N)-1:0] raddr,
    output wire [P*W-1:0] rdata
);
    localparam A = $clog2(N);
    reg [W-1:0] t [0:N-1];
    always @(posedge clk) if (we) t[waddr] <= wdata;
    genvar i;
    generate
        for (i = 0; i < P; i = i + 1) begin : g_port
            assign rdata[i*W +: W] = t[raddr[i*A +: A]];
        end
    endgenerate
endmodule
