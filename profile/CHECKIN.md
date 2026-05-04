# Check-in Prompts

## Morning Brief
At around 8am generate a morning brief with:
1. Today's calendar events (time, title, location if any)
2. Overdue reminders
3. Flagged emails needing action

Keep it under 10 lines. Lead with the most time-sensitive item.

# Handling new emails
- When a new email is received read the subject
- Ignore any emails that are spam or marketing
- If the subject indicates the email is relevant to the user then read the body for more context
- Do NOT mark the email as read
- If an email is time critical then immediately alert the user via Telegram
- If an email is related to a booking then:
  - look for a `.ics` attachment and add it to the users default calendar
  - if no `.ics` is present then use the body text to determine time, date and location before adding it to the default calendar
- If an email contains a task then ask the user via Telegram if they wish to create a reminder


## Idle Check-in
"Can I help you with anything else?"
