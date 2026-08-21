Contradictions to resolve
Message replay. Player actions include "Request that a message be repeated", but The way the game is played says "it will not be displayed again". Pick one — this is the hinge of the whole experiment.
> My bad: messages are only displayed one  

Score display. Scoring proposes four player-facing categories (Station Safety, Operational Efficiency, Crew Satisfaction, Incident Awareness); Scoring system says the player sees accumulated negative points. Which is live-visible vs. debrief-only?
> One scoring system but with debrief and where the issues where from.

Priority hierarchy vs. Event 7 Stage 4. The hierarchy puts Security emergency (3) above Medical emergency (4), but Stage 4 has Medical override Security's close order on D4 and treats that as correct. Also "Emergency life safety" (1) isn't distinguished from "Medical emergency" (4).
> No priority in events, ignore that

In-fiction clock. Messages use absolute times ("14:20", "at 14:35", "closed until 14:32") but the UI spec only mentions an elapsed-time timer. Absolute deadlines are unanswerable without a station clock.
> All scenario events times are relative to the start of the scenario, the station clock needs to be the same as the computer.

LLM generation vs. experimental control. Scenario balancing requires paired scenarios with equivalent cognitive structure, but The way the stories are written has the LLM generate threads, timings and messages fresh per game. Free generation destroys the equivalence the A/B comparison depends on. No equivalence mechanism is specified.
> Let's have some LLM generated and saved scenarios json format

Answer format. Keeper challenge examples are open-ended ("Correct answer: Technician Ruiz entered the service corridor"), but the gameplay section says multiple choice.
> Let's have 4 choices + I don't know

Scope. 7 special events + continuous everyday traffic, in 20–30 minutes, while Difficulty progression says 2–3 concurrent threads. These don't fit together.
> 3 to 4 concurrent threads are more appropriate, indeed

Unmapped locations. Events reference Corridor 4, Corridor 7, observation deck, service corridor, Extension Epsilon — none in the room list, and no topology exists.
> I don't understand. I will let you define a layout and some rooms for the space station, I will make changes on the go. Maybe 6 rooms with 3 corridor room ?

Door states. locked and temporarily unavailable appear in the interface spec but no mechanic ever sets them or says what the player can do about them.
> Ignore the temporary available doors mention. Doors can't be disabled by the scenario

The single biggest gap: the correctness model
Nothing in the spec defines how the system decides an action was right or wrong. Everything else (scoring, failure messages, the whole research dataset) hangs off this. Concretely, I need one of these:

(a) Constraint-stack model — each door carries a stack of active constraints ({door, required_state, reason, source, since, until_condition}). At any instant the door's expected state is the highest-priority active constraint. Penalty accrues while actual ≠ expected. Naturally handles "medical passes through, then the engineering restriction becomes active again."
(b) Discrete task model — the scenario is a list of tasks {door, target_state, window_start, window_end, failure_message}. Correct = action inside the window. Simpler, matches your "failed message per task" idea, but can't express "D8 must stay closed for 12 minutes while 4 people ask for it."
I'd recommend (a) as the truth model with (b) layered on top as the scheduling/eventing mechanism — the constraint stack is exactly the ground truth the Keeper app would visualise, so building it gives you the experiment for free.
> I would have it implemented this way : Messages can have task(s). A task is a condition and a time. Once the time is reached, the condition is checked and results are given. A condition would be a list of states (door_1:close, door_2:open). You can challenge me on this if I missed something.

Q1. Which model? And if (a): is penalty per-second of violation, or one penalty per violation episode?
Q2. What is the response-time tolerance for a request ("Open H2" → how many seconds before it counts as delayed)? Does it differ by priority tier?
Q3. Missed obligations: if the player never closes H4 after the crew returns, when does the system score it as "forgotten"? At the next message on that door, at a fixed timeout, or at end of shift?
> Penalty are fixed amount (the same for all task, no ponderation)
> The times are precise, no tolerances
> If the message says "In 2min, Have the door opened at least 30 sec before closing them right afterward", this could be translated to two tasks if the message was sent at 13:00 : [{time:"15:00", Door_3: open, "fail_message": "You did'nt have the doors opened"}, {time:"15:30", Door_3: open, "fail_message": "You shut the doors before the end of..."}, {time:"15:40", Door_3: closed, "fail_message": "You didn't close the doors"} ]  You can challenge me on this if I missed something. 
> Note : The time of the tasks need to take into consideration the time the user have to read the messages / listen to the audio, add this to the prompt that will generate the scenarios.

Timeline & simulation
Q4. Is the timeline absolute (messages fire on a fixed schedule regardless of player action) or reactive (the thread waits for the player)? E.g. "Crew clear. Close H4" is nonsense if H4 was never opened. Does the thread block, skip, or fire a failure branch?
Q5. Time is 1:1 real-time, I assume — "six minutes" = six real minutes? That means one long restriction eats a quarter of the session.
Q6. Does the clock pause while a message modal is open? Critical. If yes, no pressure. If no, messages can pile up during a modal — what happens to a second message arriving then? (Queue? Notification counter?)
Q7. How faithful is the movement simulation? Three options: (i) pure decoration — animations are scripted, door states don't affect them; (ii) actors walk the door graph and physically block on closed doors; (iii) full pressure/atmosphere sim. (i) is far cheaper; (ii) is what makes "Resident trapped between D3 and D4" emerge naturally rather than being scripted. Which?
Q8. Is there a real pressure model, or is pressure purely narrative?
> Relative time
> Let's say that there is some imediate tasks ("Open the door now"), this is not displayed if the door is already opened. To check if those doors are completed
> The scenario is build with what door are opened or closed to try to avoid those situations.
> No clock pause when reading messages, time is 1 1
> No animations for now, even for opened and closed doors, just a visual representation of the state of the doors. No person or ship movement for now.

Station topology
Q9. The map is fixed forever, so it needs to be authored once and precisely: rooms, adjacency, which of D1–D10 sits on which edge, which hangar leads where. Do you want me to draft the concrete map + adjacency graph as a proposal for you to edit? (The scenario generator can't reason about routes without it.)
Q10. Are all 15 doors in play every game, or does a scenario use a subset?
Q11. Semantics of locked vs closed, and of temporarily unavailable: can the player operate them at all? Is "H3 forced open" a state the player cannot fix (and therefore not a scored failure)?
> Draft dans display the first version of the map before creating the scenarios.
> Doors are : Opened or closed, no locked or unavailable doors. 
> A scenario can use all or a subset of the doors, but the player will always see all the doors and their state. Two different scenarios can use the same door for different tasks. 

Messages, memory & the experiment
Q12. Assuming no replay: is there truly zero message history UI in Condition A? (I think yes, and that's the point — but confirm, because it's severe.)
Q13. Are pen and paper / notes allowed or forbidden in Condition A? This must be fixed, not "if allowed" — it changes what you're measuring.
Q14. Does the modal show who is calling before the player opens it? (Affects triage behaviour.)
Q15. Radio messages: can they be replayed, and does replaying cost points or time?
Q16. Which actor types communicate by radio vs. text, and do automated station alerts get a synthetic voice?
> No history at all
> Pen and paper are allowed in A, you don't have to consider the two conditions in the game creation
> We don't know who is calling before the player opens the message an how urgent is the message. The scenario need to take in consideration the time to read the message before playing the next message, but messages can stack if the player is too slow to read them, we only see the earliest message. If a task is failed before the message is read, the player will be informed of the failure and the message will be removed from the stack.

Keeper challenges
Q17. MCQ only? How many options — always 4? One correct, or multi-select?
Q18. Is answering mandatory and blocking ("needs to answer correctly to continue") or answer-and-move-on? The spec says both in different places.
Q19. Is there a time limit on answering? Does the world keep running?
Q20. How many challenges per session, and how are they placed — fixed cadence, or triggered when a thread has been dormant N minutes (which would be a better memory probe)?
Q21. Distractor design: wrong options must be plausible (other real threads in this game). Should the generator be required to draw distractors from actual active threads?
> Yes, 4 choices, one correct answer
> Answering is mandatory and blocking, the world keeps running.
> 3 question during the session, 3 at the end of the session, they are placed starting from the middle of the session, it's written in the scenario, but the generator can place them at different times in the scenario.
> No time limit on answering, but the world keeps running.
> Yes, the possible answers can be drawn from the actual threads in the game, they must be plausible.

The Keeper application (Condition B)
This is the thing being evaluated and it is completely unspecified.

Q22. Is it in scope for this repository, or a separate app you already have / will build?
Q23. Is it auto-populated from game ground truth, or does the player have to enter information manually? If auto-populated with the truth, Condition B is trivially winnable and measures nothing about memory — it measures reading speed. What's the intended answer?
Q24. If it's a panel in the same UI: does it show the door-reason table, a thread timeline, a provenance chain, active reminders? Which of the three Keepers are separate views vs. one integrated view?
Q25. Is condition assignment within-subject (same participant plays A then B on paired scenarios) or between-subject? This determines whether you need the paired-scenario machinery at all.
> Ignore condition B

Scenario generation
Q26. Live per-game generation, or a curated bank? My recommendation: LLM generates offline into a reviewed scenario bank; the game at runtime is a deterministic player of a scenario JSON. You get reproducibility, no cold-start latency, no risk of an unsolvable game in front of a participant, and paired scenarios can be human-verified as equivalent. Live generation with a progress bar is a nice demo but a poor research instrument.
Q27. What's the fixed skeleton the LLM fills? I'd expect the structure (thread count, phase timing, constraint durations, conflict positions, challenge slots) to be a hand-authored template, with the LLM only writing names, prose and flavour. Agree?
Q28. Does a generated scenario go through a validator before play? It needs one: every "close after" has a preceding open, no two constraints on one door are contradictory-and-unresolvable, every constraint has a release event, no deadline is physically unreachable, total message density within bounds. Want me to spec the validation rules?
Q29. Target volumes for a 20–30 min session — I'd propose ~55–75 messages, 3 special threads + invasion finale, ~12–18 everyday events, 6–8 challenges. Do those feel right?
Q30. Is Event 7 (invasion) always the finale, and are the other 6 sampled?
Q31. Is the LLM used at runtime at all (grading free-text, dynamic reactions), or only at generation time?
> Generated bank, a button allow for new scenario to be generated
> Yes, a json template.
> Yes, a validator is needed, add to the rules that if a task closes a door, the next task that needs the door don't require it to be closed again, expept if it's in the future (A task can ask to have the door opened in 5 minutes, another task can ask to have the door opened right now and closed afterward), do a spec for the validator.
> Those numbers Sounds good, let it be at least 4 thread, an invasion sould not always be the finale, it can be antoher major event.
> The LLM should not have to be used at runtime, exept if I'm wrong

Actors
Q32. Name the fixed 5–6 actor types (I count 8 in the spec: Security, Construction, Maintenance, Cargo, Medical, Civilian, Command, Automated). Which get cut or merged?
Q33. One voice per type — so all security teams sound identical? That weakens provenance-tracking (distinguishing Team Alpha from Team Beta). Intentional?
> Sounds good, let's have 6 actors : Security, Construction, Cargo, Medical, Civilian, system. One voice per type. The actors are always a unique person and the same through a scenario. No voices cant be used by a group of person. Messages could be from a group of person. An actor could mention a group of person.

Technical
Q34. LLM abstraction: I'd suggest LiteLLM (thin, provider-agnostic) or pydantic-ai (typed structured output — a big win for generating validated scenario JSON). Preference?
Q35. TTS: main fork is local/offline (Piper — free, fast, distinct voice models, runs in Docker) vs. cloud API (OpenAI TTS / ElevenLabs — better quality, needs network + key). Also: pre-generate all audio during the loading bar (recommended — no runtime latency, no mid-session failure), or stream on demand?
Q36. Server-authoritative clock with SSE/WebSocket push, I assume? What happens on browser refresh mid-game — resume, or session void?
Q37. Home page says "no configuration at the moment", but the experiment needs at minimum a participant ID, a condition (A/B) and a scenario ID. Add them now?
Q38. Research data export — CSV/JSON of the full event log per session? What granularity (every click, every modal open/close, every dwell time)? "Number of times information had to be rechecked" and "response time" need explicit instrumentation.
Q39. File-based DB with concurrent games: one JSON per game + a flat index, written atomically? Any need to survive a server restart mid-game?
Q40. Station rendering: inline SVG (crisp, clickable elements, easy CSS states) vs. Canvas. I'd pick SVG. Any Angular version constraint / existing house style?
Q41. Admin page auth — none, or a shared password?
Q42. Is there any fail state at all, or does the session always run to completion?
> Ok for litellm
> Let's have the voices pre-generated during the scenario generation and saved in the scenario folder, no runtime generation.
> The game need to be run in backend with websockets, indeed, sessions are restorable after a refresh, the game state is saved in the database. and can be seen in the admin page.
> Ignore condition ab, we have the scenarion selection, let's add a participant name
> No export
> Yes, one json per game, no need to survive a server restart mid-game
> Use canvas because we need to have a visual representation of the doors
> No passwords
> No fail state, we can remove somme session in the admin page