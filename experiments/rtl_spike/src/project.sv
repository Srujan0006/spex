// SPEX RTL timing spike top (not a design): spex_loop with two RM_IHPSG13_1P_64x64 edge macros and one
// RM_IHPSG13_1P_64x16 location-word macro, all read at the same address in the same cycle (R4.2).
// ui_in: [0] scan data, [1] table scan, [2] start, [3] macro-word scan, [4] macro write. uio: the 8 protocol pins.
// SPDX-License-Identifier: Apache-2.0
`default_nettype none

module tt_um_srujan0006_spike (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);
    // pins: 2-flop synchroniser, not reset (R4.1, S48)
    logic [7:0] s1, pins;
    always_ff @(posedge clk) begin
        s1   <= uio_in;
        pins <= s1;
    end
    // host stand-in: registered controls, and a scan chain holding one location's words and its address
    logic cfg_in, cfg_shift, start, mem_shift, mem_we;
    always_ff @(posedge clk) {mem_we, mem_shift, start, cfg_shift, cfg_in} <= ui_in[4:0];
    logic [149:0] wsc;                                          // {address 6, location word 16, edge words 128}
    always_ff @(posedge clk) if (mem_shift) wsc <= {wsc[148:0], cfg_in};

    logic [127:0] edge_q;
    logic [15:0]  lw_q;
    logic [5:0]   core_addr, loc;
    logic         core_ren, fired, viol, cfg_out;
    logic [7:0]   pout, poe;
    logic [15:0]  ts;

    spex_loop u_core (
        .clk, .rst_n, .pins, .edge_q, .lw_q, .cfg_shift, .cfg_in, .cfg_out, .start,
        .mem_addr(core_addr), .mem_ren(core_ren), .loc, .fired, .viol, .pout, .poe, .ts);

    wire [5:0] addr = mem_we ? wsc[149:144] : core_addr;
    wire       ren  = core_ren & ~mem_we;
    wire       men  = ren | mem_we;

    RM_IHPSG13_1P_64x64_c2_bm_bist u_m0 (
        .A_CLK(clk), .A_MEN(men), .A_WEN(mem_we), .A_REN(ren), .A_ADDR(addr), .A_DIN(wsc[63:0]), .A_DLY(1'b1),
        .A_DOUT(edge_q[63:0]), .A_BM({64{1'b1}}), .A_BIST_CLK(1'b0), .A_BIST_EN(1'b0), .A_BIST_MEN(1'b0),
        .A_BIST_WEN(1'b0), .A_BIST_REN(1'b0), .A_BIST_ADDR(6'd0), .A_BIST_DIN(64'd0), .A_BIST_BM(64'd0));
    RM_IHPSG13_1P_64x64_c2_bm_bist u_m1 (
        .A_CLK(clk), .A_MEN(men), .A_WEN(mem_we), .A_REN(ren), .A_ADDR(addr), .A_DIN(wsc[127:64]), .A_DLY(1'b1),
        .A_DOUT(edge_q[127:64]), .A_BM({64{1'b1}}), .A_BIST_CLK(1'b0), .A_BIST_EN(1'b0), .A_BIST_MEN(1'b0),
        .A_BIST_WEN(1'b0), .A_BIST_REN(1'b0), .A_BIST_ADDR(6'd0), .A_BIST_DIN(64'd0), .A_BIST_BM(64'd0));
    RM_IHPSG13_1P_64x16_c2 u_loc (
        .A_CLK(clk), .A_MEN(men), .A_WEN(mem_we), .A_REN(ren), .A_ADDR(addr), .A_DIN(wsc[143:128]), .A_DLY(1'b1),
        .A_DOUT(lw_q));

    assign uo_out  = {fired ^ (^ts), viol, loc};
    assign uio_out = pout;
    assign uio_oe  = poe;
    wire _unused = &{ena, cfg_out, 1'b0};
endmodule
