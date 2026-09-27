\ ============================================================================
\ splash.asm -- the title screen and game-mode choice, saved as SPLASH
\
\ The disc's !BOOT runs this first. It:
\   1. closes the !BOOT *EXEC file (so the keyboard, not the file, answers);
\   2. makes sure the resident key layouts are set (see handoff.asm): kept
\      if sealed -- they survive BREAK -- otherwise the defaults;
\   3. selects MODE 1 with the game's CMYK palette and loads the logo (the
\      disc file LOGO: a band of ready-made screen bytes, converted from
\      art/splash.png by the build) straight into screen memory;
\   4. shows a short guide -- the aim, each player's keys (from the resident
\      layouts), and how ink works -- asks for two or four players and
\      waits for 2 or 4;
\   5. turns every colour black, so that the loads which follow -- into
\      screen memory, which is where there is room -- are not seen;
\   6. loads the chosen level set (LEVELS2 or LEVELS4) to LEVEL_TEMP, and
\      runs DITHER, whose loader puts the game and the level set in place.
\      The key layouts stay resident for the game.
\
\ It runs at &1900 (BASIC's PAGE with DFS), above DFS's workspace, below
\ the screen (where the logo goes and DITHER loads) and the level set at
\ LEVEL_TEMP. Zero page &00-&03 (BASIC's, free here) holds its pointers.
\ ============================================================================

INCLUDE "asm/os.asm"
INCLUDE "build/generated/level_format.asm"
INCLUDE "asm/handoff.asm"      \ key_layouts: labels only, at &0CE0.

TEXT_COLUMN = 4                \ Everything is left-aligned here.
VDU_POINTER = &00              \ splash_vdu's block pointer.
NAME_POINTER = &02             \ print_key_name's walk through key_names.

ORG &1900
GUARD MODE1_SCREEN_BASE        \ The logo loads into the screen; DITHER too.

.splash
    LDA #&77                   \ OSBYTE &77: close any SPOOL and EXEC files.
    JSR OSBYTE
    JSR keep_or_default_keys   \ The resident key layouts.

    LDX #LO(splash_setup)      \ MODE 1, no cursor, the CMYK palette.
    LDY #HI(splash_setup)
    LDA #splash_setup_end - splash_setup
    JSR splash_vdu
    LDX #LO(splash_palette)
    LDY #HI(splash_palette)
    LDA #splash_palette_end - splash_palette
    JSR splash_vdu

    LDX #LO(load_logo)         \ *LOAD LOGO: into screen memory.
    LDY #HI(load_logo)
    JSR OSCLI

    LDX #LO(splash_guide)      \ The aim and the ink.
    LDY #HI(splash_guide)
    LDA #splash_guide_end - splash_guide
    JSR splash_vdu
    JSR print_all_keys         \ Each player's keys.
    LDX #LO(splash_prompt)     \ Ask for two or four players.
    LDY #HI(splash_prompt)
    LDA #splash_prompt_end - splash_prompt
    JSR splash_vdu

.splash_key
    JSR OSRDCH                 \ A = the key pressed; carry set on Escape.
    BCC splash_key_read
    LDA #&7E                   \ Acknowledge the Escape and ask again.
    JSR OSBYTE
    JMP splash_key
.splash_key_read
    LDX #LO(load_levels_two)
    LDY #HI(load_levels_two)
    CMP #'2'
    BEQ splash_chosen
    LDX #LO(load_levels_four)
    LDY #HI(load_levels_four)
    CMP #'4'
    BNE splash_key
.splash_chosen
    STX splash_command         \ Keep the *LOAD command while the palette
    STY splash_command+1       \ goes black.
    LDX #LO(splash_blackout)
    LDY #HI(splash_blackout)
    LDA #splash_blackout_end - splash_blackout
    JSR splash_vdu
    LDX splash_command
    LDY splash_command+1
    JSR OSCLI                  \ *LOAD LEVELSn: to LEVEL_TEMP.
    LDX #LO(run_game)
    LDY #HI(run_game)
    JMP OSCLI                  \ *RUN DITHER. Never returns.

\ splash_vdu: send A bytes from X (low), Y (high) to OSWRCH.
.splash_vdu
    STX VDU_POINTER
    STY VDU_POINTER+1
    TAX
    LDY #0
.splash_vdu_byte
    LDA (VDU_POINTER),Y
    JSR OSWRCH
    INY
    DEX
    BNE splash_vdu_byte
    RTS

\ ----------------------------------------------------------------------------
\ The resident key layouts (handoff.asm)
\ ----------------------------------------------------------------------------

\ keep_or_default_keys: keep key_layouts if the block is sealed (its magic
\ and checksum right: it survived a BREAK), else fill it with the defaults
\ and seal it. A, X corrupted.
.keep_or_default_keys
    LDA handoff_magic
    CMP #HANDOFF_MAGIC
    BNE keep_or_default_keys_default
    JSR handoff_sum
    CMP handoff_checksum
    BEQ keep_or_default_keys_done
.keep_or_default_keys_default
    LDX #HANDOFF_KEY_BYTES - 1
.keep_or_default_keys_copy
    LDA default_key_layouts,X
    STA key_layouts,X
    DEX
    BPL keep_or_default_keys_copy
    \ Fall through to seal it.

\ seal_keys: mark key_layouts as set (magic and checksum). A, X corrupted.
.seal_keys
    LDA #HANDOFF_MAGIC
    STA handoff_magic
    JSR handoff_sum
    STA handoff_checksum
.keep_or_default_keys_done
    RTS

\ handoff_sum: A = the sum (mod 256) of key_layouts and handoff_magic, which
\ follows it. X corrupted.
.handoff_sum
    ASSERT handoff_magic = key_layouts + HANDOFF_KEY_BYTES
    LDA #0
    LDX #HANDOFF_KEY_BYTES
.handoff_sum_byte
    CLC
    ADC key_layouts,X
    DEX
    BPL handoff_sum_byte
    RTS

\ ----------------------------------------------------------------------------
\ Showing the keys
\
\ Each player's line, in its colour (K's in Y: black would not show), from
\ KEYS_ROW down: "<Ink>: <up> <left> <down> <right>, <fire> fires", or
\ "cursor keys" for the four directions when they are exactly those. Keys
\ are named from key_names. A line stops at KEY_LINE_LENGTH characters,
\ short of column 39 (see tools/dontdither/gen_tables.py, layout_line,
\ which the tests compare with).
\ ----------------------------------------------------------------------------

.print_all_keys
    LDX #0
.print_all_keys_slot
    STX key_slot
    JSR print_keys
    LDX key_slot
    INX
    CPX #HANDOFF_KEY_BYTES DIV KEY_LAYOUT_BYTES
    BNE print_all_keys_slot
    RTS

\ print_keys: player key_slot's line. A, X, Y corrupted.
.print_keys
    LDA #17                    \ Its colour...
    JSR OSWRCH
    LDX key_slot
    LDA ink_text_colours,X
    JSR OSWRCH
    LDA #31                    \ ...its row...
    JSR OSWRCH
    LDA #TEXT_COLUMN
    JSR OSWRCH
    LDA key_slot
    CLC
    ADC #KEYS_ROW
    JSR OSWRCH
    LDA #KEY_LINE_LENGTH       \ ...and a fresh allowance of characters.
    STA line_room

    LDA #LO(ink_names)         \ The player's name: the key_slot'th of
    STA NAME_POINTER           \ ink_names.
    LDA #HI(ink_names)
    STA NAME_POINTER+1
    LDX key_slot
    BEQ print_keys_name
.print_keys_skip_name
    JSR skip_name
    DEX
    BNE print_keys_skip_name
.print_keys_name
    LDY #&FF
    JSR print_name_at
    LDA #':'
    JSR key_char
    LDA #' '
    JSR key_char

    LDA key_slot               \ layout_start = key_slot * KEY_LAYOUT_BYTES
    ASL A
    ASL A
    CLC
    ADC key_slot
    ASSERT KEY_LAYOUT_BYTES = 5
    STA layout_start

    LDX #3                     \ The cursor keys, exactly? (Directions in
.print_keys_cursor             \ display order: up, left, down, right.)
    LDA layout_start
    CLC
    ADC display_offsets,X
    TAY
    LDA key_layouts,Y
    CMP cursor_key_codes,X
    BNE print_keys_directions
    DEX
    BPL print_keys_cursor
    LDX #LO(cursor_keys_text)
    LDY #HI(cursor_keys_text)
    JSR print_text
    JMP print_keys_fire

.print_keys_directions
    LDX #0
.print_keys_direction
    STX key_index
    LDA layout_start
    CLC
    ADC display_offsets,X
    TAY
    LDA key_layouts,Y
    JSR print_key_name
    LDX key_index
    CPX #3
    BEQ print_keys_fire
    LDA #' '
    JSR key_char
    INX
    BNE print_keys_direction   \ (Always.)

.print_keys_fire
    LDA #','
    JSR key_char
    LDA #' '
    JSR key_char
    LDY layout_start           \ Fire is first in the stored order.
    LDA key_layouts,Y
    JSR print_key_name
    LDX #LO(fires_text)
    LDY #HI(fires_text)
    JMP print_text             \ Tail call.

\ print_key_name: print the name of the key whose negative-INKEY code is A
\ ("?" if it has none). X preserved.
.print_key_name
    STA key_code
    LDA #LO(key_names)
    STA NAME_POINTER
    LDA #HI(key_names)
    STA NAME_POINTER+1
.print_key_name_find
    LDY #0
    LDA (NAME_POINTER),Y
    BEQ print_key_name_unknown \ The end of the table.
    CMP key_code
    BEQ print_key_name_found
    INC NAME_POINTER           \ Past the code...
    BNE print_key_name_skip
    INC NAME_POINTER+1
.print_key_name_skip
    JSR skip_name              \ ...and the name.
    JMP print_key_name_find
.print_key_name_found
    LDY #0                     \ The name follows the code.
    \ Fall through.

\ print_name_at: print the name after (NAME_POINTER),Y up to and including
\ its character with bit 7 set. X preserved.
.print_name_at
    INY
    LDA (NAME_POINTER),Y
    PHA
    AND #&7F
    JSR key_char
    PLA
    BPL print_name_at
    RTS

.print_key_name_unknown
    LDA #'?'
    JMP key_char

\ skip_name: move NAME_POINTER past the name it points at (up to and
\ including the character with bit 7 set). X preserved.
.skip_name
    LDY #0
.skip_name_char
    LDA (NAME_POINTER),Y
    INY
    ASL A                      \ Bit 7 into carry.
    BCC skip_name_char
    TYA                        \ NAME_POINTER += Y.
    CLC
    ADC NAME_POINTER
    STA NAME_POINTER
    BCC skip_name_done
    INC NAME_POINTER+1
.skip_name_done
    RTS

\ print_text: print the text at X (low), Y (high), ending with a character
\ with bit 7 set.
.print_text
    STX NAME_POINTER
    STY NAME_POINTER+1
    LDY #&FF
    JMP print_name_at

\ key_char: print character A if the line has room left. X, Y preserved.
.key_char
    PHA
    LDA line_room
    BEQ key_char_full
    DEC line_room
    PLA
    JMP OSWRCH                 \ (Preserves A, X, Y.)
.key_char_full
    PLA
    RTS

\ ----------------------------------------------------------------------------
\ Data
\ ----------------------------------------------------------------------------

.splash_command   EQUW 0
.key_slot         EQUB 0       \ print_keys: the player slot.
.layout_start     EQUB 0       \ Its layout's offset in key_layouts.
.key_index        EQUB 0       \ The direction being shown.
.key_code         EQUB 0       \ print_key_name: the key sought.
.line_room        EQUB 0       \ Characters the line has room for.

.ink_text_colours              \ Each player's text colour: its ink, but Y
    EQUB 1, 2, 3, 3            \ for K (logical colours 1 = C, 2 = M, 3 = Y).

.display_offsets               \ The directions in display order -- up, left,
    EQUB 4, 2, 3, 1            \ down, right -- as offsets in a layout (stored
                               \ fire, right, left, down, up).

.cursor_keys_text
    EQUS "cursor key", 's' OR &80
.fires_text
    EQUS " fire", 's' OR &80

.splash_setup
    EQUB 22, 1                 \ MODE 1.
    EQUB 23, 1, 0, 0, 0, 0, 0, 0, 0, 0   \ Cursor off.
.splash_setup_end

INCLUDE "build/generated/splash_data.asm"

\ Under the logo (character rows LOGO_TOP_ROW to LOGO_TOP_ROW + LOGO_ROWS - 1),
\ in groups a row apart:
AIM_ROW    = LOGO_TOP_ROW + LOGO_ROWS + 1   \ the aim;
PROMPT_ROW = AIM_ROW + 2       \ two lines asking for two or four players;
KEYS_ROW   = PROMPT_ROW + 3    \ each player's keys, a line each;
INK_ROW    = KEYS_ROW + 5      \ three lines on how ink works.
ASSERT INK_ROW + 2 <= 31
ASSERT TEXT_COLUMN + KEY_LINE_LENGTH <= 39   \ Short of the last column.

.splash_prompt                 \ Two lines under the logo, in the players'
    EQUB 17, 1                 \ colours (logical 1 = C, 2 = M, 3 = Y).
    EQUB 31, TEXT_COLUMN, PROMPT_ROW
    EQUS "Press "
    EQUB 17, 3
    EQUS "2"
    EQUB 17, 1
    EQUS " for two players"
    EQUB 31, TEXT_COLUMN, PROMPT_ROW + 1
    EQUS "   or "
    EQUB 17, 3
    EQUS "4"
    EQUB 17, 2
    EQUS " for four players"
.splash_prompt_end

.splash_guide                  \ In yellow (logical colour 3).
    EQUB 17, 3
    EQUB 31, TEXT_COLUMN, AIM_ROW
    EQUS "Paint as much as you can!"
    EQUB 31, TEXT_COLUMN, INK_ROW
    EQUS "Firing uses ink. Move faster and"
    EQUB 31, TEXT_COLUMN, INK_ROW + 1
    EQUS "recharge on your own colour; the"
    EQUB 31, TEXT_COLUMN, INK_ROW + 2
    \ (Short of column 39: printing in the bottom-right character cell would
    \ make the MOS scroll the screen.)
    EQUS "more saturated, the better."
.splash_guide_end
ASSERT splash_guide_end - splash_guide < 256   \ splash_vdu counts in a byte.

.splash_blackout               \ Logical colours 1-3 to black (0 already is).
    EQUB 19, 1, 0, 0, 0, 0
    EQUB 19, 2, 0, 0, 0, 0
    EQUB 19, 3, 0, 0, 0, 0
.splash_blackout_end

.load_logo
    EQUS "LOAD LOGO", 13
.load_levels_two
    EQUS "LOAD LEVELS2", 13
.load_levels_four
    EQUS "LOAD LEVELS4", 13
.run_game
    EQUS "RUN DITHER", 13

.splash_end

SAVE "SPLASH", splash, splash_end, splash
