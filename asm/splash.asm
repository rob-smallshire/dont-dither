\ ============================================================================
\ splash.asm -- the title screen and game-mode choice, saved as SPLASH
\
\ The disc's !BOOT runs this first. It:
\   1. closes the !BOOT *EXEC file (so the keyboard, not the file, answers);
\   2. selects MODE 1 with the game's CMYK palette and loads the logo (the
\      disc file LOGO: a band of ready-made screen bytes, converted from
\      art/splash.png by the build) straight into screen memory;
\   3. shows a short guide -- the aim, each keyboard player's keys, and how
\      ink works -- asks for two or four players and waits for 2 or 4;
\   4. turns every colour black, so that the loads which follow -- into
\      screen memory, which is where there is room -- are not seen;
\   5. loads the chosen level set (LEVELS2 or LEVELS4) to LEVEL_TEMP, and
\      runs DITHER, whose loader puts the game and the level set in place.
\
\ It runs at &0900, in MOS buffer pages (RS423/cassette, soft keys) that are
\ unused at boot and clear of both screen memory and DFS's workspace.
\ ============================================================================

INCLUDE "asm/os.asm"
INCLUDE "build/generated/level_format.asm"

TEXT_COLUMN = 4                \ Everything is left-aligned here.

ORG &0900
GUARD &0D00                    \ &0D00 holds the DFS NMI routine.

.splash
    LDA #&77                   \ OSBYTE &77: close any SPOOL and EXEC files.
    JSR OSBYTE

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

    LDX #LO(splash_guide)      \ The aim, the keys and the ink.
    LDY #HI(splash_guide)
    LDA #splash_guide_end - splash_guide
    JSR splash_vdu
    LDX #LO(splash_keys)       \ Each player's keys.
    LDY #HI(splash_keys)
    LDA #splash_keys_end - splash_keys
    JSR splash_vdu
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
    STX &00                    \ (zero page &00-&01: BASIC's, free here)
    STY &01
    TAX
    LDY #0
.splash_vdu_byte
    LDA (&00),Y
    JSR OSWRCH
    INY
    DEX
    BNE splash_vdu_byte
    RTS

.splash_command
    EQUW 0

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

.splash_guide                  \ In the players' colours (logical 1 = C,
    EQUB 17, 3                 \ 2 = M, 3 = Y).
    EQUB 31, TEXT_COLUMN, AIM_ROW
    EQUS "Paint as much as you can!"
    EQUB 17, 3
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
