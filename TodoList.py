todo_list = []

def show_tasks():
    if not todo_list:
        print("\nNo tasks in the list.")
    else:
        print("\nYour To-Do List:")
        for i, task in enumerate(todo_list, start=1):
            print(f"{i}. {task}")

while True:
    print("\n--- To-Do List Menu ---")
    print("1. Add Task")
    print("2. View Tasks")
    print("3. Remove Task")
    print("4. Exit")

    choice = input("Enter your choice (1-4): ")

    if choice == "1":
        task = input("Enter task: ")
        todo_list.append(task)
        print("Task added!")

    elif choice == "2":
        show_tasks()

    elif choice == "3":
        show_tasks()
        try:
            task_no = int(input("Enter task number to remove: "))
            removed = todo_list.pop(task_no - 1)
            print(f"Removed task: {removed}")
        except (ValueError, IndexError):
            print("Invalid task number!")

    elif choice == "4":
        print("Goodbye 👋")
        break

    else:
        print("Invalid choice. Please try again.")
