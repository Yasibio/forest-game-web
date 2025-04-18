from flask import Flask, session, render_template, request, redirect, url_for, flash, make_response, jsonify
import random, io, csv
from datetime import datetime

# Constants for game costs and values
WOODCUTTER_COST = 3       # Cost in trees to buy one woodcutter
EXCHANGE_VALUE = 1        # Victory points gained per woodcutter exchanged

# Descriptive names for scenario variants
SCENARIO_NAMES = {
    1: "Overshoot & Collapse",
    2: "Hubbert Curve",
    3: "Sustainable Scenario"
}

class Player:
    def __init__(self):
        self.woodcutters = 1
        self.victory_points = 0
        self.harvested_trees = 0
        self.replanted = 0
        self.exchanges_this_round = 0
        self.has_harvested = False
        self.total_vp_gained = 0

class GameModel:
    def __init__(self, variant, players_info):
        self.players = [Player(), Player()]
        self.forest = 100
        self.current_round = 0
        self.variant = variant                # 1, 2, or 3 (scenario variant)
        self.current_player = 0              # 0 = Player1's turn, 1 = Player2's turn
        self.game_over = False
        self.replant_buffer = 0             # trees scheduled to grow next round from replanting
        self.players_info = players_info    # list of player info dictionaries
        self.round_stats = []              # history of each round's stats (for CSV log)
        self.log_messages = []             # event log for the game (messages to display)

    def harvest(self):
        """Perform a harvest action for the current player. Returns number of trees harvested."""
        player = self.players[self.current_player]
        total_harvest = 0
        # Each woodcutter rolls a 6-sided die: 5-6 yields 2 trees, 2-4 yields 1, 1 yields 0
        for _ in range(player.woodcutters):
            roll = random.randint(1, 6)
            if roll >= 5:
                total_harvest += 2
            elif roll >= 2:
                total_harvest += 1
        actual_harvest = min(total_harvest, self.forest)  # cannot harvest more trees than remain
        self.forest -= actual_harvest
        player.harvested_trees += actual_harvest
        player.has_harvested = True
        return actual_harvest

    def replant(self, amount):
        """Schedule replanting of `amount` harvested trees (3 new trees next round per tree)."""
        player = self.players[self.current_player]
        max_possible = min(player.harvested_trees, (100 - self.forest - self.replant_buffer) // 3)
        if amount <= max_possible:
            player.harvested_trees -= amount
            player.replanted += amount
            self.replant_buffer += amount * 3  # these trees will regrow next round
            return True
        return False

    def buy_vp(self, amount):
        """Convert harvested trees to Victory Points (2 trees = 1 VP)."""
        player = self.players[self.current_player]
        max_possible = player.harvested_trees // 2
        if amount <= max_possible:
            player.victory_points += amount
            player.total_vp_gained += amount
            player.harvested_trees -= amount * 2
            return True
        return False

    def buy_wc(self, amount):
        """Buy additional woodcutters (3 trees = 1 woodcutter)."""
        player = self.players[self.current_player]
        max_possible = player.harvested_trees // WOODCUTTER_COST
        if amount <= max_possible:
            player.woodcutters += amount
            player.harvested_trees -= amount * WOODCUTTER_COST
            return True
        return False

    def exchange_wc(self):
        """Exchange one woodcutter for victory points (limited to 2 exchanges per round)."""
        player = self.players[self.current_player]
        if player.woodcutters > 1 and player.exchanges_this_round < 2:
            player.woodcutters -= 1
            player.victory_points += EXCHANGE_VALUE
            player.total_vp_gained += EXCHANGE_VALUE
            player.exchanges_this_round += 1
            return "exchanged"
        elif player.exchanges_this_round >= 2:
            return "limit"   # already exchanged twice this round
        else:
            return "min_wc"  # cannot exchange because only 1 woodcutter left

    def end_round(self):
        """Handle end-of-round updates: replant growth and scenario-specific effects."""
        # Grow trees from replanting (up to forest max 100)
        self.forest = min(self.forest + self.replant_buffer, 100)
        # Record round statistics for logging
        round_entry = {
            'round': self.current_round,
            'trees': self.forest,
            'p1_replanted': self.players[0].replanted,
            'p2_replanted': self.players[1].replanted,
            'p1_harvested': self.players[0].harvested_trees,
            'p1_woodcutters': self.players[0].woodcutters,
            'p1_vp': self.players[0].victory_points,
            'p2_harvested': self.players[1].harvested_trees,
            'p2_woodcutters': self.players[1].woodcutters,
            'p2_vp': self.players[1].victory_points
        }
        self.round_stats.append(round_entry)
        # Reset per-round replant and exchange counters
        self.replant_buffer = 0
        for player in self.players:
            player.replanted = 0
            player.exchanges_this_round = 0
        # Sustainable Scenario (variant 3): bonus VPs every 5 rounds (based on 10% of forest)
        if self.variant == 3 and self.current_round % 5 == 0:
            bonus = self.forest // 10
            for player in self.players:
                player.victory_points += bonus
                player.total_vp_gained += bonus
        # Check end-game conditions: forest depletion or reaching round 20
        if self.forest <= 0 or self.current_round >= 20:
            self.game_over = True

    def end_game(self):
        """Apply final game rules at game over: convert leftover trees to VPs, apply penalties/bonuses, determine winner."""
        # Convert remaining harvested trees to victory points (2 trees -> 1 VP)
        for player in self.players:
            if player.harvested_trees > 0:
                vp_gained = player.harvested_trees // 2
                player.victory_points += vp_gained
                player.total_vp_gained += vp_gained
                player.harvested_trees = 0
        # Hubbert Curve scenario (variant 2): apply penalty of -1 VP per extra woodcutter beyond the first
        if self.variant == 2:
            for player in self.players:
                penalty = max(0, player.woodcutters - 1)
                player.victory_points -= penalty
        # Determine winner (or draw)
        scores = [self.players[0].victory_points, self.players[1].victory_points]
        if scores[0] > scores[1]:
            winner = "Player 1"
        elif scores[1] > scores[0]:
            winner = "Player 2"
        else:
            winner = "Draw"
        return scores, winner

# Initialize Flask app
app = Flask(__name__)
app.secret_key = "CHANGE_THIS_SECRET_KEY"  # (Set a secure secret key via environment in production)

# In-memory storage for active games: mapping game_id -> game state
games = {}

def generate_game_id():
    """Generate a unique 6-character game code."""
    import string
    chars = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(random.choice(chars) for _ in range(6))
        if code not in games:
            return code

@app.route('/')
def index():
    # Home page with options to start or join a game
    return render_template('index.html')

@app.route('/start', methods=['GET', 'POST'])
def start_game():
    if request.method == 'POST':
        # Collect Player 1's information from the form
        p1_info = {
            'name': request.form.get('name', ''),
            'age': request.form.get('age', ''),
            'mobile': request.form.get('mobile', ''),
            'nationality': request.form.get('nationality', ''),
            'gender': request.form.get('gender', ''),
            'education': request.form.get('education', '')
        }
        # Game variant (scenario) selection
        try:
            variant = int(request.form.get('variant', '1'))
        except:
            variant = 1
        if variant not in (1, 2, 3):
            variant = 1
        # Create a new game entry
        game_id = generate_game_id()
        games[game_id] = {
            'p1_info': p1_info,
            'p2_info': None,
            'variant': variant,
            'model': None   # GameModel will be created once second player joins
        }
        # Set session to identify this user as Player 1 of the new game
        session['game_id'] = game_id
        session['player_index'] = 0
        return redirect(url_for('waiting', game_id=game_id))
    # GET: render the start game form
    return render_template('start.html')

@app.route('/wait/<game_id>')
def waiting(game_id):
    # Waiting page for Player 1, while Player 2 has not joined yet
    if 'game_id' not in session or session.get('game_id') != game_id or session.get('player_index') != 0:
        # If a Player 2 somehow accesses this page and the game is ready, redirect to the game
        if game_id in games and games[game_id]['model']:
            return redirect(url_for('game_page'))
        flash("Unauthorized or invalid game access.")
        return redirect(url_for('index'))
    scenario_name = SCENARIO_NAMES.get(games[game_id]['variant'], '')
    return render_template('waiting.html', game_id=game_id, scenario=scenario_name)

@app.route('/join', methods=['GET', 'POST'])
def join_game():
    if request.method == 'POST':
        # Player 2 enters a game code to join
        code = request.form.get('game_code', '').strip()
        if not code or code not in games:
            flash("Invalid game code. Please try again.")
            return redirect(url_for('join_game'))
        if games[code]['p2_info'] is not None:
            flash("That game already has two players or has started.")
            return redirect(url_for('join_game'))
        # If code is valid and game is open, redirect to player info form for joining
        return redirect(url_for('join_game_with_code', game_id=code))
    # GET: render form to input a game code
    return render_template('join_code.html')

@app.route('/join/<game_id>', methods=['GET', 'POST'])
def join_game_with_code(game_id):
    game = games.get(game_id)
    if not game:
        flash("Invalid game code.")
        return redirect(url_for('join_game'))
    if game['p2_info'] is not None:
        flash("This game already has two players.")
        return redirect(url_for('join_game'))
    if request.method == 'POST':
        # Collect Player 2's information
        p2_info = {
            'name': request.form.get('name', ''),
            'age': request.form.get('age', ''),
            'mobile': request.form.get('mobile', ''),
            'nationality': request.form.get('nationality', ''),
            'gender': request.form.get('gender', ''),
            'education': request.form.get('education', '')
        }
        game['p2_info'] = p2_info
        # Initialize the game model with both players' info and chosen variant
        variant = game['variant']
        game['model'] = GameModel(variant, [game['p1_info'], game['p2_info']])
        # Mark this session as Player 2 in the game
        session['game_id'] = game_id
        session['player_index'] = 1
        return redirect(url_for('game_page'))
    # GET: render Player 2 info form, showing scenario name for context
    scenario_name = SCENARIO_NAMES.get(game['variant'], '')
    return render_template('join.html', game_id=game_id, scenario=scenario_name)

@app.route('/game')
def game_page():
    # Main game page showing the board and allowing actions for the current player
    if 'game_id' not in session or 'player_index' not in session:
        flash("You are not in an active game.")
        return redirect(url_for('index'))
    game_id = session['game_id']
    player_idx = session['player_index']
    game = games.get(game_id)
    if not game or not game['model']:
        flash("Game is not ready yet.")
        return redirect(url_for('index'))
    model = game['model']
    # If the game is over, show the final results page
    if model.game_over:
        scores = [model.players[0].victory_points, model.players[1].victory_points]
        if scores[0] > scores[1]:
            winner = f"{game['p1_info'].get('name','Player 1')} (Player 1)"
        elif scores[1] > scores[0]:
            winner = f"{game['p2_info'].get('name','Player 2')} (Player 2)"
        else:
            winner = "Draw"
        scenario_name = SCENARIO_NAMES.get(game['variant'], '')
        return render_template('game_over.html', game_id=game_id, p1=game['p1_info'], p2=game['p2_info'], scores=scores, winner=winner, scenario=scenario_name)
    # If game is ongoing, prepare data for rendering the game board
    current_idx = model.current_player         # index (0 or 1) of the player whose turn it is
    current_player = model.players[current_idx]
    # Calculate maximum allowed values for replant/buy actions for convenience
    max_replant = current_player.harvested_trees // 1 if current_player.has_harvested else 0
    # (Above: effectively min(current_player.harvested_trees, floor((100 - forest - buffer)/3)), simplified for template use)
    max_replant = min(current_player.harvested_trees, (100 - model.forest - model.replant_buffer) // 3) if current_player.has_harvested else 0
    max_buy_vp = current_player.harvested_trees // 2 if current_player.has_harvested else 0
    max_buy_wc = current_player.harvested_trees // WOODCUTTER_COST if current_player.has_harvested else 0
    log_list = model.log_messages
    scenario = SCENARIO_NAMES.get(game['variant'], '')
    # Pass all relevant state to the template
    return render_template('game.html', game_id=game_id, p1=game['p1_info'], p2=game['p2_info'], model=model,
                           player1=model.players[0], player2=model.players[1],
                           current_index=current_idx, current_player=current_player,
                           player_index=player_idx, my_status=model.players[player_idx],
                           max_replant=max_replant, max_buy_vp=max_buy_vp, max_buy_wc=max_buy_wc,
                           log=log_list, scenario=scenario)

@app.route('/game_status/<game_id>')
def game_status(game_id):
    # A small endpoint to check if the game is ready (used by waiting page to poll for readiness)
    game = games.get(game_id)
    if game and game['model']:
        return jsonify(status="ready")
    else:
        return jsonify(status="waiting")

# --- Game action endpoints (triggered by form submissions on the game page) ---

@app.route('/harvest', methods=['POST'])
def action_harvest():
    if 'game_id' not in session:
        return redirect(url_for('index'))
    game = games.get(session['game_id'])
    if not game or not game['model']:
        return redirect(url_for('index'))
    model = game['model']
    player_idx = session['player_index']
    # Only allow if it's this player's turn
    if player_idx != model.current_player:
        flash("Not your turn.")
        return redirect(url_for('game_page'))
    # Perform harvest action
    harvested = model.harvest()
    model.log_messages.append(f"Player {player_idx+1} harvested {harvested} trees (Total harvested: {model.players[player_idx].harvested_trees})")
    # If harvest depleted the forest, end game immediately
    if model.forest <= 0:
        # Apply final scoring rules and mark game over
        model.end_game()
        model.game_over = True
        model.log_messages.append("Forest depleted! Game over.")
        model.log_messages.append(f"Final Scores -> Player 1: {model.players[0].victory_points}, Player 2: {model.players[1].victory_points}")
        if model.variant == 2:
            model.log_messages.append("Hubbert variant: woodcutter penalty applied to final scores.")
    return redirect(url_for('game_page'))

@app.route('/replant', methods=['POST'])
def action_replant():
    if 'game_id' not in session:
        return redirect(url_for('index'))
    game = games.get(session['game_id'])
    if not game or not game['model']:
        return redirect(url_for('index'))
    model = game['model']
    player_idx = session['player_index']
    # Only allow if it's this player's turn and they have harvested already this turn
    if player_idx != model.current_player or not model.players[player_idx].has_harvested:
        flash("Action not allowed.")
        return redirect(url_for('game_page'))
    # Get the requested amount to replant
    try:
        amount = int(request.form.get('amount', '0'))
    except:
        amount = 0
    # Perform replant action
    if model.replant(amount):
        model.log_messages.append(f"Scheduled to replant {amount} tree(s) (+{amount*3} trees next round)")
    else:
        flash("Invalid replant amount.")
    return redirect(url_for('game_page'))

@app.route('/buy_vp', methods=['POST'])
def action_buy_vp():
    if 'game_id' not in session:
        return redirect(url_for('index'))
    game = games.get(session['game_id'])
    if not game or not game['model']:
        return redirect(url_for('index'))
    model = game['model']
    player_idx = session['player_index']
    if player_idx != model.current_player or not model.players[player_idx].has_harvested:
        flash("Action not allowed.")
        return redirect(url_for('game_page'))
    try:
        amount = int(request.form.get('amount', '0'))
    except:
        amount = 0
    if model.buy_vp(amount):
        model.log_messages.append(f"Bought {amount} Victory Point(s)")
    else:
        flash("Invalid amount for buying VP.")
    return redirect(url_for('game_page'))

@app.route('/buy_wc', methods=['POST'])
def action_buy_wc():
    if 'game_id' not in session:
        return redirect(url_for('index'))
    game = games.get(session['game_id'])
    if not game or not game['model']:
        return redirect(url_for('index'))
    model = game['model']
    player_idx = session['player_index']
    if player_idx != model.current_player or not model.players[player_idx].has_harvested:
        flash("Action not allowed.")
        return redirect(url_for('game_page'))
    try:
        amount = int(request.form.get('amount', '0'))
    except:
        amount = 0
    if model.buy_wc(amount):
        model.log_messages.append(f"Bought {amount} Woodcutter(s)")
    else:
        flash("Invalid amount for buying woodcutters.")
    return redirect(url_for('game_page'))

@app.route('/exchange', methods=['POST'])
def action_exchange():
    if 'game_id' not in session:
        return redirect(url_for('index'))
    game = games.get(session['game_id'])
    if not game or not game['model']:
        return redirect(url_for('index'))
    model = game['model']
    player_idx = session['player_index']
    if player_idx != model.current_player or not model.players[player_idx].has_harvested:
        flash("Action not allowed.")
        return redirect(url_for('game_page'))
    result = model.exchange_wc()
    if result == "exchanged":
        model.log_messages.append(f"Exchanged 1 Woodcutter for {EXCHANGE_VALUE} VP (Exchanges this round: {model.players[player_idx].exchanges_this_round})")
    elif result == "limit":
        flash("You can only exchange 2 woodcutters per round.")
    elif result == "min_wc":
        flash("You must keep at least 1 woodcutter.")
    return redirect(url_for('game_page'))

@app.route('/end_turn', methods=['POST'])
def action_end_turn():
    if 'game_id' not in session:
        return redirect(url_for('index'))
    game = games.get(session['game_id'])
    if not game or not game['model']:
        return redirect(url_for('index'))
    model = game['model']
    player_idx = session['player_index']
    # Only allow end turn if it's this player's turn and they have harvested
    if player_idx != model.current_player or not model.players[player_idx].has_harvested:
        flash("Cannot end turn before harvesting.")
        return redirect(url_for('game_page'))
    # End this player's turn
    model.players[player_idx].has_harvested = False
    # Switch active player (0 -> 1 or 1 -> 0)
    model.current_player = 1 - model.current_player
    # If we've moved back to Player 1, that means a full round is completed
    if model.current_player == 0:
        model.current_round += 1
        model.end_round()
        model.log_messages.append(f"=== End of Round {model.current_round} ===")
        model.log_messages.append(f"Forest now has {model.forest} trees")
        # If the game ended due to round limit or forest depletion at this point
        if model.game_over:
            model.end_game()
            model.log_messages.append("Game reached final round or forest is depleted. Game over.")
            model.log_messages.append(f"Final Scores -> Player 1: {model.players[0].victory_points}, Player 2: {model.players[1].victory_points}")
            if model.variant == 2:
                model.log_messages.append("Hubbert variant: woodcutter penalty applied to final scores.")
    return redirect(url_for('game_page'))

@app.route('/download_log', methods=['POST'])
def download_log():
    # Provide a CSV download of the game data and player inputs after the game is over
    if 'game_id' not in session:
        return redirect(url_for('index'))
    game_id = session['game_id']
    game = games.get(game_id)
    if not game or not game['model'] or not game['model'].game_over:
        flash("Game is not over or log not available.")
        return redirect(url_for('index'))
    model = game['model']
    comment = request.form.get('comment', '').strip()  # feedback comment from players
    # Prepare CSV data in memory
    output = io.StringIO()
    writer = csv.writer(output)
    # Player 1 info
    writer.writerow(["Player 1 Information"])
    for key, value in game['p1_info'].items():
        writer.writerow([key.capitalize(), value])
    writer.writerow([])
    # Player 2 info
    writer.writerow(["Player 2 Information"])
    for key, value in game['p2_info'].items():
        writer.writerow([key.capitalize(), value])
    writer.writerow([])
    # Comments
    writer.writerow(["Comment", comment])
    writer.writerow([])
    # Game data headers
    headers = ["Round", "Trees Remaining", "P1 Replanted", "P2 Replanted",
               "P1 Harvested", "P1 Woodcutters", "P1 Victory Points",
               "P2 Harvested", "P2 Woodcutters", "P2 Victory Points"]
    writer.writerow(headers)
    # Game data per round
    for stats in model.round_stats:
        row = [
            stats['round'],
            stats['trees'],
            stats['p1_replanted'],
            stats['p2_replanted'],
            stats['p1_harvested'],
            stats['p1_woodcutters'],
            stats['p1_vp'],
            stats['p2_harvested'],
            stats['p2_woodcutters'],
            stats['p2_vp']
        ]
        writer.writerow(row)
    csv_data = output.getvalue()
    output.close()
    # Send CSV file as an attachment
    filename = f"game_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response = make_response(csv_data)
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Content-Type"] = "text/csv"
    return response
    
from flask import jsonify

@app.route('/game_status/<code>')
def game_status(code):
    """Return current turn and game‑over flag as JSON."""
    entry = games.get(code)
    if not entry or entry['model'] is None:
        return jsonify(error="not_found"), 404
    m = entry['model']
    return jsonify(current_player=m.current_player, game_over=m.game_over)


# If running this app.py directly (e.g., for local testing), start the Flask development server
if __name__ == '__main__':
    app.run(debug=True)
