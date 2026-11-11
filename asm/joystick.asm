\ ============================================================================
\ joystick.asm -- joysticks through SPItFIRE
\
\ SPItFIRE (a Master Compact peripheral, with its own sideways ROM) provides
\ up to four joysticks. This module uses only the ROM's documented interface
\ (the SPItFIRE repository's docs/joystick-programming.md); it must match
\ tools/dontdither/joysticks.py.
\
\ Detection, once at start-up, asks SPItFIRE through spitfire.asm (shared
\ with SPLASH, which shows what it found). Without SPItFIRE, or with it not
\ ready, there are no joysticks and the game is played on the keyboard alone.
\
\ Reading: every joystick has a switch byte, which SPItFIRE's firmware
\ builds from the stick and its button -- fire in bit 0, and left, down, up
\ and right in bits 4-7, a direction set when the stick is more than a
\ quarter of full scale from the centre (two adjacent ones: a diagonal).
\ OSBYTE &80 (ADVAL) on channel JOYSTICK_SWITCHES_12 returns joysticks 1
\ and 2's switch bytes in X and Y; on JOYSTICK_SWITCHES_34, joysticks 3 and
\ 4's. An unallocated joystick's is 0. read_switches reads them all into
\ joystick_switches, two calls for four joysticks; the ROM refreshes them
\ 50 times a second. Joystick j is slot j-1's (C, M, Y, K).
\
\ A switch byte's direction bits are turned into a direction through
\ switch_direction, made from the keys' own table, so a joystick steers as
\ the keys do.
\
\ Without SPItFIRE nothing is read: MOS 5 would answer these channels with
\ a copy of another one.
\
\ Requires: os.asm, game_data.asm (JOYSTICK_* and switch_direction),
\ spitfire.asm, and joysticks_available, joystick_switches and
\ spitfire_block defined by the program.
\ ============================================================================

\ ----------------------------------------------------------------------------
\ detect_joysticks -- set joysticks_available (0-4) from SPItFIRE, if fitted
\
\ On entry:  spitfire_block free (only at start-up: see main.asm)
\ On exit:   joysticks_available set, joystick_switches all 0 (nothing
\            pressed); A, X, Y corrupted
\ ----------------------------------------------------------------------------

.detect_joysticks
    JSR ask_spitfire           \ Fills spitfire_block...
    JSR count_joysticks        \ ...X = the joysticks we can use.
    STX joysticks_available
    LDA #0                     \ Nothing pressed until they are read.
    LDX #SPITFIRE_MAX_JOYSTICKS - 1
.detect_joysticks_clear
    STA joystick_switches,X
    DEX
    BPL detect_joysticks_clear
    RTS

\ ----------------------------------------------------------------------------
\ read_switches -- read every joystick's switch byte into joystick_switches
\
\ Call before joystick_input or joystick_fire, once per tick or field. Reads
\ nothing without joysticks; reads joysticks 3 and 4 only if there are more
\ than two.
\
\ On exit:   joystick_switches[0..joysticks_available-1] fresh; A, X, Y
\            corrupted
\ ----------------------------------------------------------------------------

.read_switches
    LDA joysticks_available
    BEQ read_switches_done     \ No SPItFIRE (or none ready): nothing to read.
    LDA #&80                   \ OSBYTE &80: ADVAL. Joysticks 1 and 2...
    LDX #JOYSTICK_SWITCHES_12
    JSR OSBYTE
    STX joystick_switches      \ ...in X (low byte)...
    STY joystick_switches + 1  \ ...and Y (high byte).
    LDA joysticks_available
    CMP #3
    BCC read_switches_done     \ No joystick 3 or 4.
    LDA #&80                   \ Joysticks 3 and 4.
    LDX #JOYSTICK_SWITCHES_34
    JSR OSBYTE
    STX joystick_switches + 2
    STY joystick_switches + 3
.read_switches_done
    RTS

\ ----------------------------------------------------------------------------
\ joystick_input -- the input byte from player slot X's joystick
\
\ On entry:  X = slot (below joysticks_available); read_switches done
\ On exit:   A = input byte (direction | FIRE_BIT); X corrupted
\ ----------------------------------------------------------------------------

.joystick_input
    LDA joystick_switches,X
    PHA
    LSR A                      \ The direction bits (4-7) down to 0-3: an
    LSR A                      \ index into switch_direction.
    LSR A
    LSR A
    TAX
    PLA
    ASSERT JOYSTICK_FIRE = 1
    LSR A                      \ Fire (bit 0) into carry.
    LDA switch_direction,X     \ (Carry kept.)
    BCC joystick_input_done
    ORA #FIRE_BIT
.joystick_input_done
    RTS

\ ----------------------------------------------------------------------------
\ joystick_fire -- is player slot X's joystick fire button held?
\
\ On entry:  X = slot (below joysticks_available); read_switches done
\ On exit:   A = non-zero (Z clear) if held, 0 if not; X, Y preserved
\ ----------------------------------------------------------------------------

.joystick_fire
    LDA joystick_switches,X
    AND #JOYSTICK_FIRE
    RTS
