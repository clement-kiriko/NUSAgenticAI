Overview of the Solution
The Trip Planner Council is a multi-agent simulation designed to collaboratively build a personalized, day-by-day travel itinerary based on user preferences. The system features three specialized agents—a Destination Expert, a Budget Analyst, and a Scheduler Agent—each with distinct roles and capabilities.
•	The Destination Expert recommends attractions and activities based on the destination.
•	The Budget Analyst evaluates cost feasibility to ensure the trip stays within budget.
•	The Scheduler Agent organizes the chosen attractions into a coherent daily schedule with appropriate timings.
Agents communicate through a peer-to-peer coordination mechanism using shared memory to exchange preferences and negotiation results. A tool integration layer provides access to mock APIs or datasets (e.g., map or price lookup), with controlled permissions per agent to simulate real-world role-based tool access.
The system maintains both shared and individual agent states to track decisions, preferences, and updates across the planning process. Given a user prompt such as “3-day Japan trip under $1000”, the agents collaboratively generate a complete, budget-conscious itinerary while demonstrating effective state management, inter-agent communication, and coordinated decision-making.
Clear set up instructions so that your instructor (me) knows how to set it up and run it.
Set up instructions
1)	Download and unzip the code
2)	Open cmd prompt > Run “pip install poetry”
3)	Run “poetry install”
4)	Start the conversation > “python main.py”
5)	1st prompt(human): 3-day Japan trip under $1000
