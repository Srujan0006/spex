// Smoke test of the timing spike: two locations, a clock-triggered edge and a pin-triggered edge.
// Expected: 0 -(x0 >= 5)-> 1 -(pin 0 rises)-> 0 -> 1 ...
`timescale 1ns/1ps
`default_nettype none
module tb_spike;
    reg clk = 0, rst_n = 0;
    reg [7:0] ui = 0, uio = 0;
    wire [7:0] uo, uio_out, uio_oe;
    always #10 clk = ~clk;
    tt_um_srujan0006_spike dut (.ui_in(ui), .uo_out(uo), .uio_in(uio), .uio_out(uio_out), .uio_oe(uio_oe),
                                .ena(1'b1), .clk(clk), .rst_n(rst_n));
    // edge word (R11.1): target[30:25] pattern[24:22] window[21:19] ck[18:17] dk[16:14] k[13:11] action[10:7]
    //                    reset[6:4] error[3] winmsb[2] valid[1] log[0]
    function [31:0] edgew(input [5:0] tgt, input [2:0] pat, input [2:0] win, input [1:0] ck, input [2:0] rst);
        edgew = {1'b0, tgt, pat, win, ck, 3'd0, 3'd0, 4'd0, rst, 1'b0, 1'b0, 1'b1, 1'b0};
    endfunction
    integer n, fires;
    reg [5:0] trace [0:15];
    initial begin
        // tables: window 1 = {clk 0, hi 20, lo 5}; pattern 1 = {EDGE, value 1, mask 1}
        dut.u_core.cfg = 0;
        dut.u_core.cfg[1*34 +: 34] = {2'd0, 16'd20, 16'd5};
        dut.u_core.cfg[16*34 + 1*17 +: 17] = {1'b1, 8'h01, 8'h01};
        dut.u_m0.mem[0] = {32'd0, edgew(6'd1, 3'd0, 3'd1, 2'd1, 3'b001)};   // loc 0 slot 0: GE x0 >= 5, reset x0
        dut.u_m1.mem[0] = 64'd0;
        dut.u_m0.mem[1] = {32'd0, edgew(6'd0, 3'd1, 3'd0, 2'd0, 3'b000)};   // loc 1 slot 0: pin 0 rises
        dut.u_m1.mem[1] = 64'd0;
        repeat (3) @(posedge clk);
        rst_n = 1;
        @(negedge clk) ui[2] = 1;                                          // start
        @(negedge clk) ui[2] = 0;
        fires = 0;
        for (n = 0; n < 80; n = n + 1) begin
            @(negedge clk);
            uio[0] = (n % 20) >= 10;                                       // pin 0: rises every 20 cycles
            if (dut.u_core.fired && fires < 16) begin
                trace[fires] = dut.u_core.loc;
                fires = fires + 1;
            end
        end
        if (fires < 4) begin $display("FAIL: only %0d firings", fires); $fatal(1); end
        for (n = 0; n < fires; n = n + 1)
            if (trace[n] != ((n % 2 == 0) ? 6'd1 : 6'd0)) begin
                $display("FAIL: firing %0d went to %0d", n, trace[n]); $fatal(1);
            end
        $display("PASS: %0d firings alternating 1, 0", fires);
        $finish;
    end
endmodule
