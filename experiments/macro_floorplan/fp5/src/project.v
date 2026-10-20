/*
 * SPEX week-1 floorplan experiment fp5 (not a design): 4 x RM_IHPSG13_1P_64x64 (edge memory)
 * + 1 x RM_IHPSG13_1P_256x32 (coverage) with dummy logic, to test routing and precheck at 8x4.
 * Copyright (c) 2026 Srujan0006. SPDX-License-Identifier: Apache-2.0
 */
`default_nettype none
`ifndef FP_FILL
`define FP_FILL 64
`endif
module tt_um_srujan0006_fp5 (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);
    wire [4:0] d;
    fp_tile #(.AW(6), .DW(64), .FILL(`FP_FILL), .SEED(32'h0000_0001)) u_m0 (.clk(clk), .rst_n(rst_n), .din(ui_in), .dout(d[0]));
    fp_tile #(.AW(6), .DW(64), .FILL(`FP_FILL), .SEED(32'h0000_0013)) u_m1 (.clk(clk), .rst_n(rst_n), .din(ui_in ^ uio_in), .dout(d[1]));
    fp_tile #(.AW(6), .DW(64), .FILL(`FP_FILL), .SEED(32'h0000_0105)) u_m2 (.clk(clk), .rst_n(rst_n), .din(~ui_in), .dout(d[2]));
    fp_tile #(.AW(6), .DW(64), .FILL(`FP_FILL), .SEED(32'h0000_1009)) u_m3 (.clk(clk), .rst_n(rst_n), .din(uio_in), .dout(d[3]));
    fp_tile #(.AW(8), .DW(32), .FILL(`FP_FILL), .SEED(32'h0001_0021)) u_cov (.clk(clk), .rst_n(rst_n), .din(ui_in + uio_in), .dout(d[4]));
    assign uo_out = {3'b000, d};
    assign uio_out = 8'h00;
    assign uio_oe = 8'h00;
    wire _unused = &{ena, 1'b0};
endmodule
