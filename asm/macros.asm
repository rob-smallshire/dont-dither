\ ============================================================================
\ macros.asm -- assembler macros shared by all programs
\
\ beebasm requires a macro to be defined before its first use, so INCLUDE
\ this at the top of each program, before any code. It emits no bytes.
\ ============================================================================

\ ----------------------------------------------------------------------------
\ SEND_VDU block, block_end -- send the bytes block..block_end-1 to OSWRCH
\
\ A macro wrapping send_vdu_bytes so call sites read as one line.
\ Corrupts A, X, Y.
\ ----------------------------------------------------------------------------

MACRO SEND_VDU block, block_end
    LDX #LO(block)
    LDY #HI(block)
    LDA #block_end - block
    JSR send_vdu_bytes
ENDMACRO
