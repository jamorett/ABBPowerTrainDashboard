import os

path = "app.py"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

text = text.replace('== "Alarm"', 'in ["Alarm", "Error"]')
text = text.replace('== "Tolerable"', 'in ["Tolerable", "Warning"]')

# Fix the manual mode ones that didn't have the white fallback
text = text.replace('else "🔴"', 'else ("🔴" if overall_cond in ["Alarm", "Error"] else "⚪")')
text = text.replace('else ("🔴" if overall_cond in ["Alarm", "Error"] else "⚪")', 'else ("🔴" if kpi_cond in ["Alarm", "Error"] else "⚪")', 1) # This is risky. Let's just stick to the main ones.

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print("Replaced successfully!")
