# Five-minute capstone video

**Target: 4:30. Maximum: 5:00.** Record your screen and voice. Type the prompts
below as the conversation goes; buttons are optional. Use fictional details and
confirm only previews that are correct.

App: https://calvinprepetit-auto-shop.streamlit.app/

Before recording: open a fresh private window, make sure the app is awake, and
turn **Simulate API outage** off. Keep this sheet off-screen. Do one take; model
replies and loading times vary.

## 0:00–0:20 | Introduce

Show the app title and software disclosure.

**Say:** “This is my Auto Shop Service Advisor. It helps customers describe a
vehicle concern, review a technician note, schedule a visit, or create a service
ticket. A technician—not the bot—inspects the vehicle.”

## 0:20–1:30 | Concern, AI note, and summary

Type these as asked:

1. `There is a weird noise coming from my muffler.`
2. `Last week.`
3. `When driving.`
   If another follow-up appears, type `I'm not sure` rather than guessing.
4. Review the technician note and department. Type `Show my technician summary`.
5. Type `yes` to accept the note; review the summary preview, then type `yes`.

**Say:** “The AI turns the customer’s words into a clear technician note and
suggests a service area. The conversation keeps details across turns. This is
an inspection suggestion, not a diagnosis; the summary alone saves no request.”

## 1:30–2:40 | Appointment and saved record

1. Type `Schedule an appointment`.
2. Choose one of the displayed openings.
3. At the customer-details prompt, type `Calvin 2023 Honda Civic`.
4. At the preview, change the day: `Actually can I do Monday?`
5. Choose a displayed Monday time; if none is available, pick another displayed
   opening. Read the revised preview, then type `yes`.
6. Show the saved APT number.

**Say:** “Python checks openings, holds the name, vehicle, day, and time, and
saves only after I confirm the reviewed details.”

## 2:40–3:35 | Unscheduled ticket and grounded answer

1. Click **Start Over**. Type `I need my tires and oil changed`; review both jobs.
2. Type `Create a service ticket`, then `yes` to use the note for that ticket.
3. At the details prompt, type `Demo 2020 Honda Civic`; review and confirm.
4. Show the SR number and **Visit: Not scheduled**. Type `What should I bring?`
   and point out the shop-guide source.

**Say:** “This ticket records requested work without booking a visit. The shop
answer is grounded in the guide and shows its source.”

## 3:35–3:50 | Safe boundary

Type `Can you guarantee my warranty will cover this repair?`

**Say:** “The bot sends warranty decisions to the manufacturer or dealer; it
doesn’t decide or deny coverage.”

## 3:50–4:15 | Graceful failure

Click **Start Over**. Turn **Simulate API outage** on. Type `My car is making a
noise`. Show the friendly error and that no request was saved. Turn simulation off.

**Say:** “This simulated outage shows the app handles a provider failure without
breaking or saving an incomplete request. It also handles rate limits.”

## 4:15–4:30 | Improvement

**Say:** “Requests and schedules are demo-only and session-based. Next, I’d add
a shared database and real calendar dates so the shop can share persistent records.”

Stop before 5:00. If time runs short, skip the warranty example and the duplicate-
confirmation check; keep all four intents, the grounded answer, the failure, and
the improvement. Don’t confirm an incorrect preview. If the provider errors,
stop and wait for the shown cooldown before trying again. Never show API keys.
