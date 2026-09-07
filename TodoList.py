
import json
import os
from datetime import datetime

TODO_FILE = "todo_list.json"

todo_list = []


# ----------------------------------------
# Save tasks to file
# ----------------------------------------
def save_tasks():
    with open(TODO_FILE, "w") as file:
        json.dump(todo_list, file, indent=4)


# ----------------------------------------
# Load tasks from file
# ----------------------------------------
def load_tasks():
    global todo_list

    if os.path.exists(TODO_FILE):
        try:
            with open(TODO_FILE, "r") as file:
                todo_list = json.load(file)
        except (json.JSONDecodeError, FileNotFoundError):
            todo_list = []


# ----------------------------------------
# Display a single task
# ----------------------------------------
def display_task(index, task):
    status = "✓" if task["completed"] else " "

    priority = task["priority"].upper()

    print(
        f"{index}. [{status}] "
        f"{task['title']} "
        f"| Priority: {priority} "
        f"| Created: {task['created']}"
    )


# ----------------------------------------
# Show all tasks
# ----------------------------------------
def show_tasks():
    if not todo_list:
        print("\nNo tasks in the list.")
        return

    print("\n========== YOUR TO-DO LIST ==========")

    for i, task in enumerate(todo_list, start=1):
        display_task(i, task)

    print("=====================================")


# ----------------------------------------
# Add a new task
# ----------------------------------------
def add_task():
    print("\n---------- ADD TASK ----------")

    title = input("Enter task: ").strip()

    if not title:
        print("Task cannot be empty!")
        return

    print("\nPriority options:")
    print("1. Low")
    print("2. Medium")
    print("3. High")

    priority_choice = input("Choose priority (1-3): ").strip()

    priorities = {
        "1": "low",
        "2": "medium",
        "3": "high"
    }

    priority = priorities.get(priority_choice, "medium")

    task = {
        "title": title,
        "completed": False,
        "priority": priority,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M")
    }

    todo_list.append(task)

    save_tasks()

    print("✓ Task added successfully!")


# ----------------------------------------
# Remove a task
# ----------------------------------------
def remove_task():
    if not todo_list:
        print("\nThere are no tasks to remove.")
        return

    show_tasks()

    try:
        task_no = int(input("\nEnter task number to remove: "))

        if task_no < 1 or task_no > len(todo_list):
            print("Invalid task number!")
            return

        removed = todo_list.pop(task_no - 1)

        save_tasks()

        print(f"✓ Removed task: {removed['title']}")

    except ValueError:
        print("Please enter a valid number!")


# ----------------------------------------
# Mark task as completed
# ----------------------------------------
def complete_task():
    if not todo_list:
        print("\nNo tasks available.")
        return

    show_tasks()

    try:
        task_no = int(input("\nEnter task number to mark complete: "))

        if task_no < 1 or task_no > len(todo_list):
            print("Invalid task number!")
            return

        task = todo_list[task_no - 1]

        if task["completed"]:
            print("This task is already completed.")
        else:
            task["completed"] = True
            save_tasks()
            print(f"✓ Completed: {task['title']}")

    except ValueError:
        print("Please enter a valid number!")


# ----------------------------------------
# Undo completed task
# ----------------------------------------
def undo_task():
    if not todo_list:
        print("\nNo tasks available.")
        return

    show_tasks()

    try:
        task_no = int(input("\nEnter task number to mark incomplete: "))

        if task_no < 1 or task_no > len(todo_list):
            print("Invalid task number!")
            return

        task = todo_list[task_no - 1]

        if not task["completed"]:
            print("This task is already incomplete.")
        else:
            task["completed"] = False
            save_tasks()
            print(f"↩ Task reopened: {task['title']}")

    except ValueError:
        print("Please enter a valid number!")


# ----------------------------------------
# Edit a task
# ----------------------------------------
def edit_task():
    if not todo_list:
        print("\nNo tasks available.")
        return

    show_tasks()

    try:
        task_no = int(input("\nEnter task number to edit: "))

        if task_no < 1 or task_no > len(todo_list):
            print("Invalid task number!")
            return

        task = todo_list[task_no - 1]

        print(f"\nCurrent task: {task['title']}")

        new_title = input(
            "Enter new task name (press Enter to keep current): "
        ).strip()

        if new_title:
            task["title"] = new_title

        print("\nPriority:")
        print("1. Low")
        print("2. Medium")
        print("3. High")

        new_priority = input(
            "Choose new priority (press Enter to keep current): "
        ).strip()

        priorities = {
            "1": "low",
            "2": "medium",
            "3": "high"
        }

        if new_priority in priorities:
            task["priority"] = priorities[new_priority]

        save_tasks()

        print("✓ Task updated successfully!")

    except ValueError:
        print("Please enter a valid number!")


# ----------------------------------------
# Search tasks
# ----------------------------------------
def search_tasks():
    if not todo_list:
        print("\nNo tasks available.")
        return

    keyword = input("\nEnter keyword to search: ").strip().lower()

    if not keyword:
        print("Search keyword cannot be empty.")
        return

    results = []

    for task in todo_list:
        if keyword in task["title"].lower():
            results.append(task)

    if not results:
        print("\nNo matching tasks found.")
        return

    print("\n========== SEARCH RESULTS ==========")

    for i, task in enumerate(results, start=1):
        display_task(i, task)

    print("====================================")


# ----------------------------------------
# Show statistics
# ----------------------------------------
def show_statistics():
    total = len(todo_list)

    completed = sum(
        1 for task in todo_list
        if task["completed"]
    )

    pending = total - completed

    high_priority = sum(
        1 for task in todo_list
        if task["priority"] == "high"
    )

    medium_priority = sum(
        1 for task in todo_list
        if task["priority"] == "medium"
    )

    low_priority = sum(
        1 for task in todo_list
        if task["priority"] == "low"
    )

    print("\n========== TASK STATISTICS ==========")
    print(f"Total tasks       : {total}")
    print(f"Completed tasks   : {completed}")
    print(f"Pending tasks     : {pending}")
    print(f"High priority     : {high_priority}")
    print(f"Medium priority   : {medium_priority}")
    print(f"Low priority      : {low_priority}")

    if total > 0:
        percentage = (completed / total) * 100
        print(f"Completion rate   : {percentage:.1f}%")

    print("======================================")


# ----------------------------------------
# Clear completed tasks
# ----------------------------------------
def clear_completed():
    global todo_list

    completed_count = sum(
        1 for task in todo_list
        if task["completed"]
    )

    if completed_count == 0:
        print("\nThere are no completed tasks.")
        return

    confirmation = input(
        f"\nDelete {completed_count} completed task(s)? (y/n): "
    ).lower()

    if confirmation == "y":
        todo_list = [
            task for task in todo_list
            if not task["completed"]
        ]

        save_tasks()

        print("✓ Completed tasks deleted.")
    else:
        print("Operation cancelled.")


# ----------------------------------------
# Clear all tasks
# ----------------------------------------
def clear_all():
    global todo_list

    if not todo_list:
        print("\nThe task list is already empty.")
        return

    confirmation = input(
        "\nAre you sure you want to delete ALL tasks? (y/n): "
    ).lower()

    if confirmation == "y":
        todo_list = []

        save_tasks()

        print("✓ All tasks have been deleted.")
    else:
        print("Operation cancelled.")


# ----------------------------------------
# Main Menu
# ----------------------------------------
def show_menu():
    print("\n")
    print("╔════════════════════════════════════╗")
    print("║          TO-DO LIST APP            ║")
    print("╠════════════════════════════════════╣")
    print("║ 1. Add Task                        ║")
    print("║ 2. View Tasks                      ║")
    print("║ 3. Remove Task                     ║")
    print("║ 4. Mark Task Completed             ║")
    print("║ 5. Undo Completed Task             ║")
    print("║ 6. Edit Task                       ║")
    print("║ 7. Search Tasks                    ║")
    print("║ 8. Task Statistics                 ║")
    print("║ 9. Clear Completed Tasks           ║")
    print("║ 10. Clear All Tasks                ║")
    print("║ 11. Exit                           ║")
    print("╚════════════════════════════════════╝")


# ----------------------------------------
# Main Program
# ----------------------------------------

load_tasks()

print("Welcome to the To-Do List App!")

while True:

    show_menu()

    choice = input("\nEnter your choice (1-11): ").strip()

    if choice == "1":
        add_task()

    elif choice == "2":
        show_tasks()

    elif choice == "3":
        remove_task()

    elif choice == "4":
        complete_task()

    elif choice == "5":
        undo_task()

    elif choice == "6":
        edit_task()

    elif choice == "7":
        search_tasks()

    elif choice == "8":
        show_statistics()

    elif choice == "9":
        clear_completed()

    elif choice == "10":
        clear_all()

    elif choice == "11":
        save_tasks()
        print("\nGoodbye! 👋")
        break

    else:
        print("\nInvalid choice. Please select 1-11.")
