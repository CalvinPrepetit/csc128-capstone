# Short capstone recording cues

Record screen + voice. Aim for 3-4 minutes; stop before 5. One browser session,
one Start Over. Keep keys/settings off-screen; outage simulation starts OFF.
Read previews before confirming. Buttons are optional except Start Over/outage.

## 1. Concern, summary, appointment

Say: "This automated service advisor organizes concerns; it does not diagnose cars."

Type, following the bot's prompts:

1. `My muffler has rattled while driving since last week.`
   If asked for more: answer what you know, or `I'm not sure`.
2. `Show my technician summary`
3. `yes` to accept the note, then `yes` at the summary preview.
   Point out that summary review saves nothing.
4. `Schedule an appointment`
5. Choose a displayed day/time.
6. When asked: `Demo 2023 Honda Civic`
7. Review the appointment preview; `yes`. Show the APT number.

Say: "AI writes the note. Python keeps the details, checks openings, and saves only after confirmation."

## 2. Ticket and grounded answer

Click Start Over ONCE. This begins another request, not another browser session.

1. `I need my tires and oil changed`
2. `Create a service ticket`, then `yes` when asked to accept the note.
3. When asked: `Demo 2020 Honda Civic`
4. Review; `yes`. Show SR number and Visit: Not scheduled.
5. `What should I bring?` Point to the guide source.

Say: "This separate ticket books no appointment. Shop information comes from the guide."

## 3. Failure and improvement

Without restarting: turn Simulate API outage ON. Type `My car is making a noise`.
Show the friendly error/no new save. Turn simulation OFF.

Say: "Failure leaves saved records unchanged. Next, I'd add a shared database and calendar dates."

Stop. Covered: four intents, slot filling, state, AI, grounding/tools, disclosure,
graceful failure, and one improvement. Optional only if time: ask `Can you decide my warranty coverage?`
The recording complements the code/tests and six-section PDF; it does not guarantee a grade.
