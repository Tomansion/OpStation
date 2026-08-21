Where I challenged you — two holes in the checkpoint-only task model
You asked me to. Both are in spec.md §6.4.

1. Instantaneous checks are blind between checkpoints. Your three-checkpoint encoding passes if the player opens D3 at t=119, closes at t=121, reopens at t=149 — the crew was locked out for 28 of the 30 seconds. Worse, the game's central situation ("keep D8 closed for 12 minutes while four people beg you to open it") can only be sampled, so opening it between samples is free. That deletes the gameplay the game exists to test.

Fix: a hold field. {at: 120, hold: 30, require: {D3: open}} — checked every tick across the window, failure fires at the moment of violation (which is also better feedback than a delayed verdict). hold: 0 is your instantaneous case. Your example collapses from 3 tasks to 2 and now says exactly what you meant.
> Ok for hold

2. False passes. If the player never opens D3 at all, your checkpoint 1 fails — but checkpoint 3 (D3: closed) passes, because the door is closed for the wrong reason. Meanwhile checkpoints 1 and 2 both fire, so one mistake costs two penalties and earns one undeserved credit.

Fix: task groups with cascade cancellation — tasks expressing one obligation share a group_id; when one fails, later tasks in that group are cancelled. One mistake, one penalty, no false credit.
> Sounds good.

Other things worth flagging
No priority hierarchy means conflicting requests need a new encoding. With tasks as the sole ground truth, a "please open D8" temptation must be a message with no task at all, colliding with another thread's live hold. Refuse → nothing. Comply → the other thread's task fails. Validator rule V17 makes the generator prove each temptation actually collides with something.
A "perfect-player simulation" is now the core validator rule (V14). It replays the scenario with an optimal operator; if any task fails, the scenario is unsolvable and rejected. It also produces the expected-state trace, which the admin page renders against the player's actual trace.
> Ok, let's make the generator try to fix the issues in an iteration process with 5 max tries.

Your no-op rule generalised into V15 (no instruction that's already satisfied) and V16 (no redundant re-requirement), with the exception you described for future restatements after an intervening change.
Your example's times looked like a typo (message at 13:00, tasks at 15:00). All times in the spec are now integer seconds from session start, so that class of error is gone.
Radio messages carry no transcript — audio only. That's a deliberate difficulty increase and it makes TTS load-bearing rather than decorative.
> Ok

Failure notices sit at lower queue priority than messages, capped at one per group per 30s. Otherwise a failure cascade buries the very messages needed to recover.
> Ok, make those values easely customisable to adjust difficulty

Reading budget is now formalised as read_cost() plus three validator rules (V7–V9): per-message slack, a rolling 60s density cap that tightens in phase 1 and loosens in the finale, and a 6s minimum gap.
Map v1 authored: 6 rooms, 3 corridors, 5 hangar bays, three deliberately doorless passages. Hangar Bay 5 has no internal door on purpose — H5 becomes the sole barrier to the construction extension, which is a strong hook for isolation obligations. There's a canvas cell grid in §3.1.1 for the renderer.
Five remaining decisions I've defaulted; say if any is wrong:

Q-D Failure notices at lower priority than messages (above).
> I think that it would add unnecessary complexity to have a priority system, let's keep it simple and have the failure notices at the same priority as messages.
> Add in the scenario generation that a task can be cancelled in the scenario. I don't know how this would translate in the json, but "Actor1: Ignore previous instruction about closing D2" (easy), "Actor1: Ignore my previous instruction" (hard), "Actor1: Ignore actor2 previous instruction because" (harder), would be a great way to add complexity.

Q-E Cascade cancellation on failure, rather than continuing to evaluate the rest of the group.
> OK

Q-F The notification button shows a pending-message count. Workload info, not content — I judged it fair.
> Ok

Q-H Review the map's door assignments and hangar roles before generation starts, as you asked.
> Ok, please define what doors are opened or closed at the start of the scenario, let make it simple and have some doors opened and some closed at the start of every scenario, it's fixed to the space station definition. The gerenators will have to take in consideration the initial state of the doors when generating the scenario.
> The md representation is hard to read, please make a json, and a js script that displays the map in a canvas with the names and the doors.

Q-I game.md and game2.md are now fully superseded — move them to archive/?
> PLease, feel free to make a clean repository