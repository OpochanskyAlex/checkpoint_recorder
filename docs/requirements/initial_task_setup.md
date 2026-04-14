# Universal Parameter Tracker — Project Spec

## 1. Business Context

People want to track various personal metrics — fuel consumption, calories, workout weights, mood, finances, and more. The most convenient way to log data is directly in a messenger they already use daily.

---

## 2. Problem

The current process is:

- Scattered across multiple apps
- Requires opening dedicated applications manually
- Often abandoned due to inconvenience
- Does not support arbitrary custom parameters

---

## 3. Project Goal

Create a Telegram bot that:

1. Accepts data in free-text format
2. Stores history for any user-defined parameters
3. Builds trends and charts on request
4. Sends alerts when a threshold value is reached

---

## 4. Constraints

- Input only via Telegram
- No predefined categories — the user defines them freely
- One bot serves multiple users
- Data is isolated between users

---

## 5. Target Users

1. An individual tracking their health
2. A person monitoring expenses or resources
3. An athlete logging their progress

---

## 6. High-Level Functionality

### 6.0 Help

The bot must respond to a `/help` command with a formatted list of all available commands and a brief description of each.

### 6.1 Data Input

The user writes to the bot in free form:

```
fuel 40L
```
```
mood 7
```
```
bench press 80kg 5reps
```
```
calories 450
```

### 6.2 Parameter Management

- A new parameter is created automatically on first entry
- View list of own parameters
- Delete a parameter along with its history

### 6.3 History & Analytics

- Log of last N entries for a parameter
- Trend chart (image sent in chat)
- Period comparison (week / month)


## 7. Out of Scope

- Integration with fitness trackers or external APIs
- Voice input
- Multi-language support
- ML-based predictions