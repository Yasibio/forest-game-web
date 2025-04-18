# Forest Management Game (Web Version)

This project is a full-stack web implementation of the **Forest Management Board Game**, originally a local Tkinter-based Python game. Two players manage a virtual forest together, making strategic decisions to harvest and replant trees, purchase upgrades, and earn points under different scenario rules. The game has been converted to a Flask web application with a responsive HTML/JavaScript interface, making it accessible through a web browser and deployable to cloud platforms (like Render or Heroku).

## Gameplay Overview

Two players take turns performing actions each round:
- **Harvest:** Roll dice for each woodcutter to harvest trees from the forest.
- **Replant:** Replant some of the harvested trees (for every tree replanted, 3 new trees will grow in the forest next round).
- **Buy VP (Victory Points):** Convert harvested trees into victory points (2 trees = 1 point).
- **Buy Woodcutter:** Spend harvested trees to hire more woodcutters (3 trees = 1 woodcutter) for faster harvesting in future rounds.
- **Exchange Woodcutter:** Permanently trade in a woodcutter for 1 victory point (max 2 exchanges per round, and you cannot go below 1 woodcutter).
- **End Turn:** Finish your turn. After both players end their turns, the round ends and the forest may regrow based on replanting.

The game can be played in one of three scenarios (chosen at game start by Player 1):
1. **Overshoot & Collapse:** A scenario where aggressive harvesting can quickly collapse the forest.
2. **Hubbert Curve:** Harvest yields follow a peak-and-decline pattern; an end-of-game penalty is applied for having too many woodcutters (–1 point per extra woodcutter beyond the first).
3. **Sustainable Scenario:** Encourages long-term management – every 5 rounds, each player gains bonus points equal to 10% of the trees left in the forest (rewarding conservation).

The forest starts with 100 trees. The game ends if the forest is completely depleted or after 20 rounds, whichever comes first. At game end, any remaining harvested trees are converted to points (2 trees = 1 point), and scenario-specific bonuses/penalties are applied (e.g., Hubbert Curve penalty).

## Web App Features

- **Multiplayer Support:** Two players can play from different devices. Player 1 starts a game and gets a unique game code. Player 2 joins by entering that code. The app handles session management to keep track of which player is which.
- **Turn-Based Interaction:** The interface clearly indicates whose turn it is and enables the appropriate actions. Players cannot perform actions out of turn or invalid actions (buttons are disabled accordingly, and server-side checks with feedback ensure game rules are followed).
- **Real-Time Updates:** Player 1’s view will automatically update when Player 2 joins. Both players see the game state (forest status, each other’s woodcutters and points, etc.) update in real time after each action (upon form submission).
- **Game Log:** A running log of game events is displayed to all players, just like the console in the original game. It notes harvest results, actions taken, round endings, and game-over summaries.
- **Data Logging & Export:** At game end, players can enter comments/feedback and download a CSV file containing:
  - Both players’ input details (name, demographics, etc.).
  - The scenario and any final comments.
  - A round-by-round breakdown of actions (trees remaining, trees replanted, harvested, woodcutters, points for each player per round).
- **Responsive UI:** The interface uses Bootstrap for a clean layout that works on desktop or mobile browsers. It preserves clarity of information with sections for forest status, player stats, actions, and log.

## Project Structure

- **app.py:** The Flask application defining routes and game logic. This is the main backend file.
- **templates/**: Contains Jinja2 HTML templates for each page (index, start, waiting, join, game board, game over). These templates are rendered by Flask with dynamic data.
- **requirements.txt:** Lists required Python packages (Flask and Gunicorn).
- **Procfile:** Configuration for deployment, specifying how to run the web server.
- **README.md:** This documentation, explaining game rules, setup, and deployment.

## Setup and Running Locally

1. **Python Environment:** Ensure you have Python 3.8+ installed. Create a virtual environment and activate it (optional but recommended).
2. **Install Dependencies:** Run `pip install -r requirements.txt` to install Flask and Gunicorn.
3. **Run the App:** You can start the Flask development server with:
   ```bash
   python app.py

**End of README.md**