Launch 5 subagents in parallel, each playing sts2-cli as a different character (Ironclad, Silent, Defect, Regent, Necrobinder). Each subagent plays $ARGUMENTS games (default: 3) by **making its own LLM decisions** — reading JSON game state, thinking about strategy, and choosing actions.

Each subagent must:

1. Start the game process via JSON protocol
2. At each decision point, read the full state and make an intelligent choice
3. Play through complete runs (until game_over)
4. Report back:
   - **Results**: floor reached, win/loss, key moments
   - **Bugs**: crashes, template leaks `[VarName]`, untranslated text, auto-selected choices, missing data, display issues
   - **Strategy**: what worked, what didn't, hardest enemies
   - **Character-specific**: orbs (Defect), stars (Regent), osty (Necrobinder), poison/shivs (Silent)

After all 5 agents return, the main agent should:
1. Summarize all bugs across characters
2. Fix every bug found
3. Run regression test: `python3 python/test_quality.py` + `play_full_run.py 5` per character
4. Update `learning.md` with strategy learnings
5. Commit with descriptive message (ask user before pushing)

**Subagent game setup:**
```python
import json, subprocess, os
os.environ["STS2_GAME_DIR"] = os.path.expanduser("~/Library/Application Support/Steam/steamapps/common/Slay the Spire 2/SlayTheSpire2.app/Contents/Resources/data_sts2_macos_arm64")
proc = subprocess.Popen([os.path.expanduser("~/.dotnet-arm64/dotnet"), "run", "--no-build", "--project", "Sts2Headless/Sts2Headless.csproj"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
def read():
    while True:
        l = proc.stdout.readline().strip()
        if not l: return None
        if l.startswith("{"): return json.loads(l)
def send(cmd):
    proc.stdin.write(json.dumps(cmd) + "\n"); proc.stdin.flush()
    return read()
```

**Key commands:**
- `{"cmd": "start_run", "character": "Ironclad", "seed": "test_1"}`
- `{"cmd": "action", "action": "play_card", "args": {"card_index": 0, "target_index": 0}}` (target_index only for AnyEnemy cards)
- `{"cmd": "action", "action": "end_turn"}`
- `{"cmd": "action", "action": "select_map_node", "args": {"col": X, "row": Y}}`
- `{"cmd": "action", "action": "select_card_reward", "args": {"card_index": N}}` / `skip_card_reward`
- `{"cmd": "action", "action": "choose_option", "args": {"option_index": N}}`
- `{"cmd": "action", "action": "leave_room"}`
- `{"cmd": "action", "action": "select_cards", "args": {"indices": "0"}}`
- `{"cmd": "action", "action": "select_bundle", "args": {"bundle_index": 0}}`

**Decision types:** map_select, combat_play, card_reward, card_select, bundle_select, rest_site, event_choice, shop, game_over
