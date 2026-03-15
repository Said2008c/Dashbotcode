from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import os
import json
import uuid
import requests
from datetime import datetime
from functools import wraps

# ═══════════════════════════════════════════════════════════════
#             ⚙️  CONFIGURATION & INITIALIZATION
# ═══════════════════════════════════════════════════════════════
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24))

# 🦖 PTERODACTYL
PANEL_URL = os.getenv("PANEL_URL", "https://your-panel.com")
PTERO_API = os.getenv("PTERO_API_KEY", "your-application-api-key")

# 💸 SHOP UPGRADES
UPGRADES = {
    'ram_upgrade':  {'name': '2GB RAM Upgrade',    'cost': 100, 'ram': 2048, 'cpu': 0,   'disk': 0},
    'cpu_upgrade':  {'name': '1 CPU Core Upgrade', 'cost': 150, 'ram': 0,    'cpu': 100, 'disk': 0},
    'disk_upgrade': {'name': '5GB Disk Upgrade',   'cost': 75,  'ram': 0,    'cpu': 0,   'disk': 5120},
}

# 📞 SUPPORT INFO
PHONE_SUPPORT = "+1-555-SERVER-99"
DISCORD_LINK  = "https://discord.gg/AQaZh4Quyz"

# 👑 ADMIN
ADMIN_EMAIL    = "dash@dash.com"
ADMIN_PASSWORD = "72hdh7sh2uebd7en27"
ADMIN_USERNAME = "admin"

# ═══════════════════════════════════════════════════════════════
#                     📁  DATA FILES
# ═══════════════════════════════════════════════════════════════
USERS_FILE         = "web_users.json"
SERVERS_FILE       = "user_servers.json"
COUPONS_FILE       = "coupons.json"
TICKETS_FILE       = "tickets.json"
ANNOUNCEMENTS_FILE = "announcements.json"

def load_json(file):
    try:
        with open(file, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def load_json_list(file):
    try:
        with open(file, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_json(file, data):
    with open(file, 'w') as f:
        json.dump(data, f, indent=4)

# ─── bootstrap ───
def ensure_admin_exists():
    users = load_json(USERS_FILE)
    if ADMIN_USERNAME not in users:
        users[ADMIN_USERNAME] = {
            'email':          ADMIN_EMAIL,
            'password':       ADMIN_PASSWORD,
            'panel_id':       'admin',
            'coins':          999999,
            'is_admin':       True,
            'upgrades':       {'ram_upgrades': 0, 'cpu_upgrades': 0, 'disk_upgrades': 0},
            'game_data':      {'potato_clicks': 0},
            'last_afk_claim': datetime.min.isoformat(),
            'created_at':     datetime.now().isoformat(),
        }
        save_json(USERS_FILE, users)

# ═══════════════════════════════════════════════════════════════
#                  🌐  PTERODACTYL API HELPERS
# ═══════════════════════════════════════════════════════════════
def ptero_headers():
    return {
        'Authorization': f'Bearer {PTERO_API}',
        'Content-Type':  'application/json',
        'Accept':        'application/json',
    }

def fetch_nests():
    r = requests.get(f'{PANEL_URL}/api/application/nests', headers=ptero_headers())
    return r.json()['data'] if r.status_code == 200 else []

def fetch_eggs(nest_id):
    r = requests.get(f'{PANEL_URL}/api/application/nests/{nest_id}/eggs', headers=ptero_headers())
    return r.json()['data'] if r.status_code == 200 else []

def fetch_egg_details(nest_id, egg_id):
    r = requests.get(
        f'{PANEL_URL}/api/application/nests/{nest_id}/eggs/{egg_id}?include=variables',
        headers=ptero_headers()
    )
    return r.json() if r.status_code == 200 else None

def fetch_egg_with_variables(nest_id, egg_id):
    r = requests.get(
        f'{PANEL_URL}/api/application/nests/{nest_id}/eggs/{egg_id}?include=variables',
        headers=ptero_headers()
    )
    if r.status_code != 200:
        return None
    attrs = r.json()['attributes']
    variables = []
    if 'relationships' in attrs and 'variables' in attrs['relationships']:
        for var in attrs['relationships']['variables']['data']:
            v = var['attributes']
            variables.append({
                'name':          v.get('name', ''),
                'description':   v.get('description', ''),
                'env_variable':  v.get('env_variable', ''),
                'default_value': v.get('default_value', ''),
                'user_viewable': v.get('user_viewable', True),
                'user_editable': v.get('user_editable', True),
                'rules':         v.get('rules', ''),
            })
    return {
        'name':         attrs.get('name', ''),
        'description':  attrs.get('description', ''),
        'docker_image': attrs.get('docker_image', ''),
        'startup':      attrs.get('startup', ''),
        'variables':    variables,
    }

def fetch_nodes():
    r = requests.get(f'{PANEL_URL}/api/application/nodes', headers=ptero_headers())
    if r.status_code != 200:
        return []
    nodes = []
    for n in r.json().get('data', []):
        a = n['attributes']
        nodes.append({
            'id':                  a['id'],
            'name':                a['name'],
            'fqdn':                a.get('fqdn', ''),
            'memory':              a.get('memory', 0),
            'memory_overallocate': a.get('memory_overallocate', 0),
            'disk':                a.get('disk', 0),
            'disk_overallocate':   a.get('disk_overallocate', 0),
            'maintenance_mode':    a.get('maintenance_mode', False),
        })
    return nodes

def _first_free_alloc(node_id):
    try:
        r = requests.get(
            f'{PANEL_URL}/api/application/nodes/{node_id}/allocations',
            headers=ptero_headers()
        )
        if r.status_code == 200:
            for alloc in r.json().get('data', []):
                a = alloc['attributes']
                if not a.get('assigned', True):
                    return a['id']
    except Exception as e:
        print(f"Alloc fetch error node {node_id}: {e}")
    return None

def create_panel_user(username, email, password):
    r = requests.post(
        f'{PANEL_URL}/api/application/users',
        headers=ptero_headers(),
        json={'username': username, 'email': email,
              'first_name': username, 'last_name': 'User', 'password': password}
    )
    if r.status_code in [200, 201]:
        return r.json()['attributes']['id']
    print(f"PTERO CREATE USER ERROR {r.status_code}: {r.text}")
    return None

def create_server(panel_user_id, server_name, nest_id, egg_id,
                  user_resources, custom_env=None, node_id=None):
    egg = fetch_egg_details(nest_id, egg_id)
    if not egg:
        return None

    env = {}
    if 'relationships' in egg['attributes'] and 'variables' in egg['attributes']['relationships']:
        for var in egg['attributes']['relationships']['variables']['data']:
            va = var['attributes']
            env[va['env_variable']] = va.get('default_value', '')
    if custom_env:
        env.update(custom_env)

    BASE_RAM, BASE_CPU, BASE_DISK = 1024, 100, 3500
    payload = {
        'name': server_name, 'user': panel_user_id,
        'nest': nest_id, 'egg': egg_id,
        'docker_image': egg['attributes']['docker_image'],
        'startup':      egg['attributes']['startup'],
        'limits': {
            'memory': BASE_RAM + user_resources['total_ram_upgrades'],
            'swap': 0,
            'disk':   BASE_DISK + user_resources['total_disk_upgrades'],
            'io': 500,
            'cpu':    BASE_CPU + user_resources['total_cpu_upgrades'],
        },
        'feature_limits': {'databases': 1, 'backups': 1, 'allocations': 1},
        'environment': env,
    }

    if node_id:
        alloc = _first_free_alloc(node_id)
        if alloc:
            payload['node'] = node_id
            payload['allocation'] = {'default': alloc}
        else:
            payload['deploy'] = {'locations': [1], 'dedicated_ip': False, 'port_range': []}
    else:
        payload['deploy'] = {'locations': [1], 'dedicated_ip': False, 'port_range': []}

    r = requests.post(f'{PANEL_URL}/api/application/servers',
                      headers=ptero_headers(), json=payload)
    if r.status_code in [200, 201]:
        return r.json()['attributes']
    print(f"PTERO CREATE SERVER ERROR {r.status_code}: {r.text}")
    return None

def delete_panel_server(server_id):
    r = requests.delete(f'{PANEL_URL}/api/application/servers/{server_id}',
                        headers=ptero_headers())
    if r.status_code in [200, 201, 204]:
        return True
    print(f"PTERO DELETE SERVER ERROR {r.status_code}: {r.text}")
    return False

# ═══════════════════════════════════════════════════════════════
#                  🔒  DECORATORS
# ═══════════════════════════════════════════════════════════════
def login_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrap

def admin_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        users = load_json(USERS_FILE)
        if not users.get(session['username'], {}).get('is_admin', False):
            session['message'] = '❌ Access denied. Admins only.'
            session['message_type'] = 'error'
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return wrap

# ═══════════════════════════════════════════════════════════════
#                  💰  RESOURCE HELPERS
# ═══════════════════════════════════════════════════════════════
def get_user_resources(username):
    user = load_json(USERS_FILE).get(username, {})
    upg  = user.get('upgrades', {})
    return {
        'total_ram_upgrades':  upg.get('ram_upgrades',  0) * 2048,
        'total_cpu_upgrades':  upg.get('cpu_upgrades',  0) * 100,
        'total_disk_upgrades': upg.get('disk_upgrades', 0) * 5120,
    }

# ═══════════════════════════════════════════════════════════════
#                  🎟️  COUPON HELPERS
# ═══════════════════════════════════════════════════════════════
def load_coupons():
    return load_json(COUPONS_FILE)   # dict: code -> coupon_obj

def save_coupons(data):
    save_json(COUPONS_FILE, data)

def coupon_is_valid(code, username):
    """Returns (ok: bool, message: str, coupon: dict|None)"""
    coupons = load_coupons()
    code    = code.strip().upper()
    if code not in coupons:
        return False, 'Coupon not found.', None
    c = coupons[code]
    if not c.get('active', True):
        return False, 'This coupon has been disabled.', None
    if c.get('expires_at') and datetime.fromisoformat(c['expires_at']) < datetime.now():
        return False, 'This coupon has expired.', None
    max_uses = c.get('max_uses', 0)
    if max_uses > 0 and len(c.get('used_by', [])) >= max_uses:
        return False, 'This coupon has reached its usage limit.', None
    if username in c.get('used_by', []):
        return False, 'You have already used this coupon.', None
    return True, 'Valid', c

def redeem_coupon(code, username):
    """Applies coupon and returns (ok, message, coins_awarded)"""
    ok, msg, c = coupon_is_valid(code, username)
    if not ok:
        return False, msg, 0
    coupons = load_coupons()
    code    = code.strip().upper()
    coupons[code].setdefault('used_by', []).append(username)
    save_coupons(coupons)

    coins = c.get('coins', 0)
    if coins > 0:
        users = load_json(USERS_FILE)
        if username in users:
            users[username]['coins'] = users[username].get('coins', 0) + coins
            save_json(USERS_FILE, users)
    return True, f'Coupon redeemed! You received {coins} coins.', coins

# ═══════════════════════════════════════════════════════════════
#                  🎫  TICKET HELPERS
# ═══════════════════════════════════════════════════════════════
def load_tickets():
    return load_json(TICKETS_FILE)   # dict: ticket_id -> ticket_obj

def save_tickets(data):
    save_json(TICKETS_FILE, data)

def new_ticket_id():
    return 'TKT-' + str(uuid.uuid4())[:8].upper()

# ═══════════════════════════════════════════════════════════════
#                  📢  ANNOUNCEMENT HELPERS
# ═══════════════════════════════════════════════════════════════
def load_announcements():
    data = load_json(ANNOUNCEMENTS_FILE)
    if isinstance(data, list):
        return data
    return []

def save_announcements(data):
    save_json(ANNOUNCEMENTS_FILE, data)

# ═══════════════════════════════════════════════════════════════
#                  🌐  ROUTES  —  AUTH
# ═══════════════════════════════════════════════════════════════
@app.route('/')
def home():
    return redirect(url_for('dashboard') if 'username' in session else url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        users    = load_json(USERS_FILE)
        if username in users:
            error = 'Username already exists!'
        elif username.lower() == ADMIN_USERNAME:
            error = 'That username is reserved.'
        else:
            users[username] = {
                'email': email, 'password': password, 'panel_id': None,
                'coins': 50, 'is_admin': False,
                'upgrades': {'ram_upgrades': 0, 'cpu_upgrades': 0, 'disk_upgrades': 0},
                'game_data': {'potato_clicks': 0},
                'last_afk_claim': datetime.min.isoformat(),
                'created_at': datetime.now().isoformat(),
            }
            save_json(USERS_FILE, users)
            panel_id = create_panel_user(username, email, password)
            if panel_id:
                users[username]['panel_id'] = panel_id
                save_json(USERS_FILE, users)
            session['username'] = username
            return redirect(url_for('dashboard'))
    return render_template('index.html', mode='register', error=error)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    error = None
    if request.method == 'POST':
        ident    = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        users    = load_json(USERS_FILE)
        # allow email login
        actual = ident
        if '@' in ident:
            actual = next(
                (u for u, d in users.items() if d.get('email') == ident and d.get('password') == password),
                None
            )
            if actual is None:
                error = 'Invalid credentials!'
        if not error:
            if actual not in users or users[actual]['password'] != password:
                error = 'Invalid username or password!'
            else:
                session['username'] = actual
                return redirect(url_for('dashboard'))
    return render_template('index.html', mode='login', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ═══════════════════════════════════════════════════════════════
#                  🌐  ROUTES  —  DASHBOARD
# ═══════════════════════════════════════════════════════════════
@app.route('/dashboard')
@login_required
def dashboard():
    username        = session['username']
    users           = load_json(USERS_FILE)
    user_servers_db = load_json(SERVERS_FILE)
    user_data       = users.get(username, {})
    user_servers    = user_servers_db.get(username, [])
    server_count    = len(user_servers)

    coins     = user_data.get('coins', 0)
    is_admin  = user_data.get('is_admin', False)
    res       = get_user_resources(username)
    total_ram  = 1024 + res['total_ram_upgrades']
    total_cpu  = 100  + res['total_cpu_upgrades']
    total_disk = 3500 + res['total_disk_upgrades']

    nests        = fetch_nests()
    message      = session.pop('message', None)
    message_type = session.pop('message_type', 'success')

    # announcements (all users see active ones)
    announcements = [a for a in load_announcements() if a.get('active', True)]

    # user's own tickets
    all_tickets  = load_tickets()
    user_tickets = {tid: t for tid, t in all_tickets.items() if t.get('owner') == username}

    # admin extras
    all_users         = {}
    all_server_counts = {}
    all_tickets_admin = {}
    coupons           = {}
    announcements_all = []
    if is_admin:
        all_users = users
        for u in users:
            all_server_counts[u] = len(user_servers_db.get(u, []))
        all_tickets_admin = all_tickets
        coupons           = load_coupons()
        announcements_all = load_announcements()

    return render_template(
        'dashboard.html',
        username=username,
        servers=user_servers,
        server_count=server_count,
        total_ram=total_ram, total_cpu=total_cpu, total_disk=total_disk,
        nests=nests,
        panel_url=PANEL_URL,
        message=message,
        message_type=message_type,
        coins=coins,
        is_admin=is_admin,
        upgrades=UPGRADES,
        user_upgrade_counts=user_data.get('upgrades', {}),
        phone_support=PHONE_SUPPORT,
        discord_link=DISCORD_LINK,
        announcements=announcements,
        user_tickets=user_tickets,
        # admin
        all_users=all_users,
        all_server_counts=all_server_counts,
        all_tickets_admin=all_tickets_admin,
        coupons=coupons,
        announcements_all=announcements_all,
    )

# ═══════════════════════════════════════════════════════════════
#                  🌐  ROUTES  —  SERVERS
# ═══════════════════════════════════════════════════════════════
@app.route('/create-server', methods=['POST'])
@login_required
def create_server_route():
    username        = session['username']
    users           = load_json(USERS_FILE)
    user_servers_db = load_json(SERVERS_FILE)
    user_servers_db.setdefault(username, [])

    if len(user_servers_db[username]) >= 2:
        session['message'] = '⚠️ Max 2 servers reached!'
        session['message_type'] = 'warning'
        return redirect(url_for('dashboard', _anchor='create'))

    server_name = request.form.get('server_name')
    try:
        nest_id = int(request.form.get('nest_id'))
        egg_id  = int(request.form.get('egg_id'))
    except (TypeError, ValueError):
        session['message'] = '❌ Invalid Nest or Egg ID.'
        session['message_type'] = 'error'
        return redirect(url_for('dashboard', _anchor='create'))

    panel_id = users[username].get('panel_id')
    if not panel_id:
        session['message'] = '❌ Panel user not found. Contact support.'
        session['message_type'] = 'error'
        return redirect(url_for('dashboard', _anchor='create'))

    custom_env = {k[4:]: v for k, v in request.form.items() if k.startswith('env_')}
    node_id    = None
    try:
        raw = request.form.get('node_id')
        if raw:
            node_id = int(raw)
    except (TypeError, ValueError):
        pass

    server = create_server(panel_id, server_name, nest_id, egg_id,
                           get_user_resources(username),
                           custom_env=custom_env, node_id=node_id)
    if server:
        user_servers_db[username].append({
            'id': server['id'], 'uuid': server['uuid'],
            'name': server['name'],
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        })
        save_json(SERVERS_FILE, user_servers_db)
        session['message'] = f'✅ Server "{server_name}" created!'
        session['message_type'] = 'success'
    else:
        session['message'] = '❌ Server creation failed. Check logs.'
        session['message_type'] = 'error'
    return redirect(url_for('dashboard', _anchor='servers'))

@app.route('/server/delete/<int:server_id>', methods=['POST'])
@login_required
def delete_server(server_id):
    username        = session['username']
    user_servers_db = load_json(SERVERS_FILE)
    user_servers    = user_servers_db.get(username, [])
    entry = next((s for s in user_servers if s['id'] == server_id), None)
    if not entry:
        session['message'] = '❌ Server not found.'
        session['message_type'] = 'error'
        return redirect(url_for('dashboard', _anchor='servers'))
    deleted = delete_panel_server(server_id)
    user_servers_db[username] = [s for s in user_servers if s['id'] != server_id]
    save_json(SERVERS_FILE, user_servers_db)
    session['message'] = (
        f'✅ "{entry["name"]}" deleted.' if deleted
        else f'⚠️ "{entry["name"]}" removed from dashboard (panel deletion may have failed).'
    )
    session['message_type'] = 'success' if deleted else 'warning'
    return redirect(url_for('dashboard', _anchor='servers'))

# ═══════════════════════════════════════════════════════════════
#                  🌐  ROUTES  —  SHOP
# ═══════════════════════════════════════════════════════════════
@app.route('/shop/buy/<string:upgrade_key>', methods=['POST'])
@login_required
def buy_upgrade(upgrade_key):
    username  = session['username']
    users     = load_json(USERS_FILE)
    user_data = users.get(username, {})
    upgrade   = UPGRADES.get(upgrade_key)
    if not upgrade:
        session['message'] = '❌ Invalid upgrade.'; session['message_type'] = 'error'
        return redirect(url_for('dashboard', _anchor='shop'))
    cost = upgrade['cost']
    if user_data.get('coins', 0) < cost:
        session['message'] = f'❌ Not enough coins! Need {cost}.'; session['message_type'] = 'error'
        return redirect(url_for('dashboard', _anchor='shop'))
    user_data['coins'] -= cost
    key_map = {'ram_upgrade': 'ram_upgrades', 'cpu_upgrade': 'cpu_upgrades', 'disk_upgrade': 'disk_upgrades'}
    if upgrade_key in key_map:
        field = key_map[upgrade_key]
        user_data['upgrades'][field] = user_data['upgrades'].get(field, 0) + 1
    users[username] = user_data
    save_json(USERS_FILE, users)
    session['message'] = f'✅ Purchased "{upgrade["name"]}" for {cost} coins!'
    session['message_type'] = 'success'
    return redirect(url_for('dashboard', _anchor='shop'))

# ═══════════════════════════════════════════════════════════════
#                  🌐  ROUTES  —  COUPONS
# ═══════════════════════════════════════════════════════════════
@app.route('/coupon/redeem', methods=['POST'])
@login_required
def redeem_coupon_route():
    username = session['username']
    code     = request.form.get('code', '').strip().upper()
    if not code:
        session['message'] = '❌ Please enter a coupon code.'; session['message_type'] = 'error'
        return redirect(url_for('dashboard', _anchor='coupons'))
    ok, msg, _ = redeem_coupon(code, username)
    session['message'] = ('✅ ' if ok else '❌ ') + msg
    session['message_type'] = 'success' if ok else 'error'
    return redirect(url_for('dashboard', _anchor='coupons'))

# ── admin coupon management ──
@app.route('/admin/coupons/create', methods=['POST'])
@login_required
@admin_required
def admin_create_coupon():
    code      = request.form.get('code', '').strip().upper()
    coins     = int(request.form.get('coins', 0))
    max_uses  = int(request.form.get('max_uses', 0))
    expires   = request.form.get('expires_at', '').strip()  # ISO date or blank

    if not code:
        session['message'] = '❌ Coupon code cannot be empty.'; session['message_type'] = 'error'
        return redirect(url_for('dashboard', _anchor='admin-coupons'))

    coupons = load_coupons()
    if code in coupons:
        session['message'] = f'❌ Coupon "{code}" already exists.'; session['message_type'] = 'error'
        return redirect(url_for('dashboard', _anchor='admin-coupons'))

    coupons[code] = {
        'coins':      coins,
        'max_uses':   max_uses,   # 0 = unlimited
        'expires_at': expires if expires else None,
        'active':     True,
        'used_by':    [],
        'created_at': datetime.now().isoformat(),
        'created_by': session['username'],
    }
    save_coupons(coupons)
    session['message'] = f'✅ Coupon "{code}" created!'
    session['message_type'] = 'success'
    return redirect(url_for('dashboard', _anchor='admin-coupons'))

@app.route('/admin/coupons/toggle/<code>', methods=['POST'])
@login_required
@admin_required
def admin_toggle_coupon(code):
    coupons = load_coupons()
    if code in coupons:
        coupons[code]['active'] = not coupons[code].get('active', True)
        save_coupons(coupons)
        status = 'enabled' if coupons[code]['active'] else 'disabled'
        session['message'] = f'✅ Coupon "{code}" {status}.'
    else:
        session['message'] = '❌ Coupon not found.'
    session['message_type'] = 'success' if code in coupons else 'error'
    return redirect(url_for('dashboard', _anchor='admin-coupons'))

@app.route('/admin/coupons/delete/<code>', methods=['POST'])
@login_required
@admin_required
def admin_delete_coupon(code):
    coupons = load_coupons()
    if code in coupons:
        del coupons[code]
        save_coupons(coupons)
        session['message'] = f'✅ Coupon "{code}" deleted.'
        session['message_type'] = 'success'
    else:
        session['message'] = '❌ Coupon not found.'
        session['message_type'] = 'error'
    return redirect(url_for('dashboard', _anchor='admin-coupons'))

# ═══════════════════════════════════════════════════════════════
#                  🌐  ROUTES  —  TICKETS
# ═══════════════════════════════════════════════════════════════
@app.route('/tickets/open', methods=['POST'])
@login_required
def open_ticket():
    username = session['username']
    subject  = request.form.get('subject', '').strip()
    body     = request.form.get('body', '').strip()
    category = request.form.get('category', 'General').strip()

    if not subject or not body:
        session['message'] = '❌ Subject and message are required.'; session['message_type'] = 'error'
        return redirect(url_for('dashboard', _anchor='tickets'))

    tickets = load_tickets()
    tid     = new_ticket_id()
    tickets[tid] = {
        'id':         tid,
        'owner':      username,
        'subject':    subject,
        'category':   category,
        'status':     'open',           # open | in_progress | closed
        'priority':   'normal',         # normal | high | urgent
        'created_at': datetime.now().isoformat(),
        'updated_at': datetime.now().isoformat(),
        'messages': [
            {
                'author':    username,
                'is_admin':  False,
                'body':      body,
                'sent_at':   datetime.now().isoformat(),
            }
        ],
    }
    save_tickets(tickets)
    session['message'] = f'✅ Ticket {tid} opened. We\'ll get back to you soon!'
    session['message_type'] = 'success'
    return redirect(url_for('dashboard', _anchor='tickets'))

@app.route('/tickets/<tid>/reply', methods=['POST'])
@login_required
def reply_ticket(tid):
    username = session['username']
    users    = load_json(USERS_FILE)
    is_admin = users.get(username, {}).get('is_admin', False)
    body     = request.form.get('body', '').strip()

    if not body:
        session['message'] = '❌ Reply cannot be empty.'; session['message_type'] = 'error'
        return redirect(url_for('dashboard', _anchor='tickets'))

    tickets = load_tickets()
    if tid not in tickets:
        session['message'] = '❌ Ticket not found.'; session['message_type'] = 'error'
        return redirect(url_for('dashboard', _anchor='tickets'))

    t = tickets[tid]
    # non-admins can only reply to their own tickets
    if not is_admin and t.get('owner') != username:
        session['message'] = '❌ Access denied.'; session['message_type'] = 'error'
        return redirect(url_for('dashboard', _anchor='tickets'))

    t['messages'].append({
        'author':   username,
        'is_admin': is_admin,
        'body':     body,
        'sent_at':  datetime.now().isoformat(),
    })
    t['updated_at'] = datetime.now().isoformat()
    if is_admin and t['status'] == 'open':
        t['status'] = 'in_progress'

    save_tickets(tickets)
    session['message'] = '✅ Reply sent.'
    session['message_type'] = 'success'
    anchor = 'admin-tickets' if is_admin else 'tickets'
    return redirect(url_for('dashboard', _anchor=anchor))

@app.route('/tickets/<tid>/close', methods=['POST'])
@login_required
def close_ticket(tid):
    username = session['username']
    users    = load_json(USERS_FILE)
    is_admin = users.get(username, {}).get('is_admin', False)
    tickets  = load_tickets()

    if tid not in tickets:
        session['message'] = '❌ Ticket not found.'; session['message_type'] = 'error'
        return redirect(url_for('dashboard', _anchor='tickets'))

    t = tickets[tid]
    if not is_admin and t.get('owner') != username:
        session['message'] = '❌ Access denied.'; session['message_type'] = 'error'
        return redirect(url_for('dashboard', _anchor='tickets'))

    t['status'] = 'closed'
    t['updated_at'] = datetime.now().isoformat()
    save_tickets(tickets)
    session['message'] = f'✅ Ticket {tid} closed.'
    session['message_type'] = 'success'
    anchor = 'admin-tickets' if is_admin else 'tickets'
    return redirect(url_for('dashboard', _anchor=anchor))

# admin: set priority
@app.route('/admin/tickets/<tid>/priority', methods=['POST'])
@login_required
@admin_required
def admin_set_priority(tid):
    priority = request.form.get('priority', 'normal')
    tickets  = load_tickets()
    if tid in tickets:
        tickets[tid]['priority'] = priority
        tickets[tid]['updated_at'] = datetime.now().isoformat()
        save_tickets(tickets)
        session['message'] = f'✅ Priority set to {priority} for {tid}.'
    else:
        session['message'] = '❌ Ticket not found.'
    session['message_type'] = 'success'
    return redirect(url_for('dashboard', _anchor='admin-tickets'))

# admin: delete ticket
@app.route('/admin/tickets/<tid>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_ticket(tid):
    tickets = load_tickets()
    if tid in tickets:
        del tickets[tid]
        save_tickets(tickets)
        session['message'] = f'✅ Ticket {tid} deleted.'
        session['message_type'] = 'success'
    else:
        session['message'] = '❌ Ticket not found.'
        session['message_type'] = 'error'
    return redirect(url_for('dashboard', _anchor='admin-tickets'))

# ═══════════════════════════════════════════════════════════════
#                  🌐  ROUTES  —  ANNOUNCEMENTS
# ═══════════════════════════════════════════════════════════════
@app.route('/admin/announcements/create', methods=['POST'])
@login_required
@admin_required
def admin_create_announcement():
    title   = request.form.get('title', '').strip()
    body    = request.form.get('body', '').strip()
    kind    = request.form.get('kind', 'info')     # info | warning | success | danger
    pinned  = request.form.get('pinned') == 'on'

    if not title or not body:
        session['message'] = '❌ Title and body are required.'; session['message_type'] = 'error'
        return redirect(url_for('dashboard', _anchor='admin-announcements'))

    announcements = load_announcements()
    announcements.insert(0, {
        'id':         str(uuid.uuid4())[:8],
        'title':      title,
        'body':       body,
        'kind':       kind,
        'pinned':     pinned,
        'active':     True,
        'created_at': datetime.now().isoformat(),
        'created_by': session['username'],
    })
    save_announcements(announcements)
    session['message'] = '✅ Announcement published!'
    session['message_type'] = 'success'
    return redirect(url_for('dashboard', _anchor='admin-announcements'))

@app.route('/admin/announcements/<aid>/toggle', methods=['POST'])
@login_required
@admin_required
def admin_toggle_announcement(aid):
    announcements = load_announcements()
    for a in announcements:
        if a.get('id') == aid:
            a['active'] = not a.get('active', True)
            break
    save_announcements(announcements)
    session['message'] = '✅ Announcement updated.'
    session['message_type'] = 'success'
    return redirect(url_for('dashboard', _anchor='admin-announcements'))

@app.route('/admin/announcements/<aid>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_announcement(aid):
    announcements = [a for a in load_announcements() if a.get('id') != aid]
    save_announcements(announcements)
    session['message'] = '✅ Announcement deleted.'
    session['message_type'] = 'success'
    return redirect(url_for('dashboard', _anchor='admin-announcements'))

# ═══════════════════════════════════════════════════════════════
#                  🌐  ROUTES  —  ADMIN (users & coins)
# ═══════════════════════════════════════════════════════════════
@app.route('/admin/give-coins', methods=['POST'])
@login_required
@admin_required
def admin_give_coins():
    target = request.form.get('target_user')
    try:
        amount = int(request.form.get('amount', 0))
    except (ValueError, TypeError):
        amount = 0
    if amount <= 0:
        session['message'] = '❌ Amount must be > 0.'; session['message_type'] = 'error'
        return redirect(url_for('dashboard', _anchor='admin'))
    users = load_json(USERS_FILE)
    if target not in users:
        session['message'] = f'❌ User "{target}" not found.'; session['message_type'] = 'error'
        return redirect(url_for('dashboard', _anchor='admin'))
    users[target]['coins'] = users[target].get('coins', 0) + amount
    save_json(USERS_FILE, users)
    session['message'] = f'✅ Gave {amount} coins to {target}. Balance: {users[target]["coins"]}'
    session['message_type'] = 'success'
    return redirect(url_for('dashboard', _anchor='admin'))

# ═══════════════════════════════════════════════════════════════
#                  🌐  ROUTES  —  API (AJAX)
# ═══════════════════════════════════════════════════════════════
@app.route('/api/nodes')
@login_required
def api_nodes():
    return jsonify(fetch_nodes())

@app.route('/api/eggs/<int:nest_id>')
@login_required
def api_eggs(nest_id):
    return jsonify(fetch_eggs(nest_id))

@app.route('/api/egg-details/<int:nest_id>/<int:egg_id>')
@login_required
def api_egg_details(nest_id, egg_id):
    data = fetch_egg_with_variables(nest_id, egg_id)
    return jsonify(data) if data else (jsonify({'error': 'failed'}), 500)

@app.route('/api/ticket/<tid>')
@login_required
def api_ticket(tid):
    """Return a single ticket as JSON (for modal rendering)."""
    username = session['username']
    users    = load_json(USERS_FILE)
    is_admin = users.get(username, {}).get('is_admin', False)
    tickets  = load_tickets()
    t        = tickets.get(tid)
    if not t:
        return jsonify({'error': 'not found'}), 404
    if not is_admin and t.get('owner') != username:
        return jsonify({'error': 'forbidden'}), 403
    return jsonify(t)

# ═══════════════════════════════════════════════════════════════
#                     🚀  RUN SERVER
# ═══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    HOST  = os.getenv("FLASK_HOST",  "0.0.0.0")
    PORT  = int(os.getenv("FLASK_PORT", 9001))
    DEBUG = os.getenv("FLASK_DEBUG", "True").lower() in ('true', '1', 't')

    ensure_admin_exists()

    if PANEL_URL == "https://your-panel.com" or PTERO_API == "your-application-api-key":
        print("⚠️  WARNING: Pterodactyl config is using default values. Server creation will fail.")

    print(f"🚀 Server starting → http://{HOST}:{PORT}")
    print(f"👑 Admin → {ADMIN_EMAIL}")
    app.run(host=HOST, port=PORT, debug=DEBUG)
