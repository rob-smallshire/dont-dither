\ ============================================================================
\ tune.asm -- the title music on its own, saved as TUNE
\
\ *RUN TUNE (from BASIC) starts the music player (music.asm) with the title
\ theme, tells the test harness it is ready (zp_boot_status), and waits for
\ ever while the vsync event plays. For listening to the player, and for
\ testing it against the model (tests/test_music.py), apart from SPLASH.
\ ============================================================================

INCLUDE "asm/os.asm"
INCLUDE "asm/macros.asm"
INCLUDE "asm/zeropage.asm"

ORG &1900                      \ BASIC's PAGE with DFS.
GUARD &7C00                    \ MODE 7 screen memory.

.start
    LDA #0                     \ Not ready yet.
    STA zp_boot_status
    JSR music_start
    LDA #BOOT_READY
    STA zp_boot_status
.idle
    JMP idle                   \ The music plays from the vsync event.

INCLUDE "asm/music.asm"
INCLUDE "build/generated/splash_theme.asm"

.end

SAVE "TUNE", start, end, start
