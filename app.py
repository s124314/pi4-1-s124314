import dash
import requests
import pandas as pd
from dash import Dash, html, dash_table, dcc
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import plotly.express as px

# settings
NOCODB_URL = "http://localhost:8080"
TOKEN = "9wVU4w2M3YUYhxIHf1ZHSH4-CXbOqQKRo4YzZPdW"

# Tables
PROJECT_ENDPOINT = "/api/v2/tables/mqejgb1k2tepfze/records"
ORG_ENDPOINT     = "/api/v2/tables/mjd7jczb07m6a92/records"
DEPT_ENDPOINT    = "/api/v2/tables/mzw04lbx3a442o3/records" 
USER_ENDPOINT    = "/api/v2/tables/mbsjp5zwx90vd54/records"

# Projects links (linkFieldId) — из Swagger
LINK_ORG  = "co8pk00u0vkvfc5"   # Orgatisation
LINK_DEPT = "c6qs9mdgrfzippi"   # Department
LINK_USER = "cehew4lsp8xx3et"   # user

ORG_LINK_COL_IN_PROJECTS = "Orgatisation"

EDITABLE_FIELDS = ["name", "date", "address"]  # простые поля проекта
# ---------------------------------------------------


def headers():
    return {"xc-token": TOKEN, "Content-Type": "application/json"}


def fetch_df(endpoint, limit=500, offset=0):
    url = f"{NOCODB_URL}{endpoint}?limit={limit}&offset={offset}"
    r = requests.get(url, headers=headers(), timeout=15)
    r.raise_for_status()
    data = r.json()
    rows = data.get("list", data if isinstance(data, list) else [])
    return pd.DataFrame(rows)


def create_record(endpoint, payload):
    url = f"{NOCODB_URL}{endpoint}"
    r = requests.post(url, headers=headers(), json=payload, timeout=15)
    r.raise_for_status()
    return r.json()


def patch_record(endpoint, payload):
    # PATCH /records с {"Id":..., ...}
    url = f"{NOCODB_URL}{endpoint}"
    r = requests.patch(url, headers=headers(), json=payload, timeout=15)
    r.raise_for_status()
    return r.json()


def delete_record(endpoint, record_id):
    # DELETE /records с {"Id":...}
    url = f"{NOCODB_URL}{endpoint}"
    r = requests.delete(url, headers=headers(), json={"Id": int(record_id)}, timeout=15)
    r.raise_for_status()
    return True


def link_record(project_id: int, link_field_id: str, target_id: int):
    """
    POST /api/v2/tables/<projectTableId>/links/<linkFieldId>/records/<recordId>
    recordId = project_id
    """
    url = f"{NOCODB_URL}/api/v2/tables/mqejgb1k2tepfze/links/{link_field_id}/records/{int(project_id)}"

    # вариант 1
    r = requests.post(url, headers=headers(), json={"Id": int(target_id)}, timeout=15)
    if r.status_code in (200, 201):
        return True

    # вариант 2
    r2 = requests.post(url, headers=headers(), json={"ids": [int(target_id)]}, timeout=15)
    r2.raise_for_status()
    return True


# ---------- нормализация (чтобы DataTable не падал на dict/list) ----------
def to_cell_value(x):
    if x is None:
        return None
    if isinstance(x, (str, int, float, bool)):
        return x

    if isinstance(x, list):
        parts = []
        for item in x:
            if isinstance(item, dict):
                for key in ("Id", "id", "name", "title"):
                    if key in item:
                        parts.append(str(item[key]))
                        break
                else:
                    parts.append(str(item))
            else:
                parts.append(str(item))
        return ", ".join(parts)

    if isinstance(x, dict):
        for key in ("Id", "id", "name", "title"):
            if key in x:
                return str(x[key])
        return str(x)

    return str(x)


def normalize_for_table(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in df.columns:
        if df[col].apply(lambda v: isinstance(v, (dict, list))).any():
            df[col] = df[col].apply(to_cell_value)
    return df
# ------------------------------------------------------------------------


def guess_label_col(df):
    for c in ["name", "Name", "title", "Title"]:
        if c in df.columns:
            return c
    for c in df.columns:
        if c not in ["Id", "CreatedAt", "UpdatedAt"]:
            return c
    return "Id"


def to_options(df):
    if df.empty:
        return []
    label_col = guess_label_col(df)
    opts = []
    for _, r in df.iterrows():
        if "Id" not in r:
            continue
        try:
            opts.append({"label": str(r.get(label_col, r["Id"])), "value": int(r["Id"])})
        except Exception:
            pass
    return opts


def id_to_name_map(df):
    if df.empty or "Id" not in df.columns:
        return {}
    label_col = guess_label_col(df)
    m = {}
    for _, r in df.iterrows():
        try:
            m[int(r["Id"])] = str(r.get(label_col, r["Id"]))
        except Exception:
            pass
    return m


def extract_ids(value):
    """
    Достаёт список Id из разных форматов связи:
    - 5
    - "5"
    - "5, 7"
    - [{"Id":5},{"Id":7}]
    - {"Id":5}
    """
    if value is None:
        return []
    if isinstance(value, int):
        return [value]
    if isinstance(value, float):
        return [int(value)]
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",") if p.strip()]
        ids = []
        for p in parts:
            try:
                ids.append(int(p))
            except Exception:
                pass
        return ids
    if isinstance(value, dict):
        for k in ("Id", "id"):
            if k in value:
                try:
                    return [int(value[k])]
                except Exception:
                    return []
        return []
    if isinstance(value, list):
        out = []
        for item in value:
            out.extend(extract_ids(item))
        return out
    return []


def prepare_projects(df):
    df = df.copy()
    df["_delete"] = "Удалить"
    return df


def make_columns(df):
    cols = []
    for c in df.columns:
        if c == "_delete":
            cols.append({"name": "", "id": "_delete", "presentation": "markdown"})
        else:
            cols.append({"name": c, "id": c, "editable": (c in EDITABLE_FIELDS)})
    return cols


def make_projects_by_org_chart(projects_raw: pd.DataFrame, org_df: pd.DataFrame):
    """
    Считает сколько проектов у каждой организации.
    Поддерживает случаи, когда у проекта несколько организаций (many-to-many):
    один проект будет засчитан каждой организации.
    """
    if projects_raw.empty:
        return {}

    link_col = ORG_LINK_COL_IN_PROJECTS if ORG_LINK_COL_IN_PROJECTS in projects_raw.columns else None
    if link_col is None:
        for cand in ["Organisation", "Organization", "Org", "org"]:
            if cand in projects_raw.columns:
                link_col = cand
                break
    if link_col is None:
        return {}

    org_map = id_to_name_map(org_df)

    # развернём проекты: (org_id) для подсчёта
    rows = []
    for _, r in projects_raw.iterrows():
        org_ids = extract_ids(r.get(link_col))
        for oid in org_ids:
            rows.append({"org_id": oid})

    if not rows:
        return px.bar(pd.DataFrame({"Organisation": [], "projects": []}),
                      x="Organisation", y="projects",
                      title="Сколько проектов у каждой организации")

    tmp = pd.DataFrame(rows)
    counts = tmp.groupby("org_id").size().reset_index(name="projects")
    counts["Organisation"] = counts["org_id"].map(org_map).fillna(counts["org_id"].astype(str))
    counts = counts.sort_values("projects", ascending=False)

    return px.bar(counts, x="Organisation", y="projects", title="Сколько проектов у каждой организации")


# app
app = Dash(__name__)

# initial load (справочники)
org_df = fetch_df(ORG_ENDPOINT)
dept_df = pd.DataFrame()
user_df = pd.DataFrame()
try:
    dept_df = fetch_df(DEPT_ENDPOINT)
except Exception:
    dept_df = pd.DataFrame()
try:
    user_df = fetch_df(USER_ENDPOINT)
except Exception:
    user_df = pd.DataFrame()

org_opts = to_options(org_df)
dept_opts = to_options(dept_df)
user_opts = to_options(user_df)

# initial projects load
projects_raw = fetch_df(PROJECT_ENDPOINT)
projects_df = prepare_projects(normalize_for_table(projects_raw))

app.layout = html.Div(
    style={"fontFamily": "Arial", "padding": "20px"},
    children=[
        html.H2("Projects: Данные из NocoDB"),

        html.Div(
            style={"display": "flex", "gap": "10px", "flexWrap": "wrap", "marginBottom": "10px"},
            children=[
                dcc.Input(id="p_name", placeholder="name", type="text"),
                dcc.Input(id="p_date", placeholder="date (YYYY-MM-DD)", type="text"),
                dcc.Input(id="p_address", placeholder="address", type="text"),

                dcc.Dropdown(id="p_org",  options=org_opts,  placeholder="Orgatisation", style={"minWidth": 240}),
                dcc.Dropdown(id="p_dept", options=dept_opts, placeholder="Department",  style={"minWidth": 240}),
                dcc.Dropdown(id="p_user", options=user_opts, placeholder="user",        style={"minWidth": 240}),

                html.Button("Добавить проект", id="btn_add"),
                html.Button("Сохранить правки", id="btn_save"),
                html.Button("Обновить", id="btn_refresh"),
            ],
        ),

        html.Div(id="msg", style={"marginBottom": "10px"}),

        dcc.Graph(id="chart", figure=make_projects_by_org_chart(projects_raw, org_df)),

        dash_table.DataTable(
            id="table",
            data=projects_df.to_dict("records"),
            columns=make_columns(projects_df),
            editable=True,
            page_size=10,
            filter_action="native",
            sort_action="native",
            style_table={"overflowX": "auto"},
            markdown_options={"html": False},
        ),
    ],
)

@app.callback(
    Output("table", "data"),
    Output("chart", "figure"),
    Output("msg", "children"),
    Input("btn_add", "n_clicks"),
    Input("btn_save", "n_clicks"),
    Input("btn_refresh", "n_clicks"),
    Input("table", "active_cell"),
    State("table", "data"),
    State("p_name", "value"),
    State("p_date", "value"),
    State("p_address", "value"),
    State("p_org", "value"),
    State("p_dept", "value"),
    State("p_user", "value"),
    prevent_initial_call=True,
)
def actions(add_clicks, save_clicks, refresh_clicks, active_cell, table_data,
            name, date, address, org_id, dept_id, user_id):

    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    trigger = ctx.triggered[0]["prop_id"].split(".")[0]

    try:
        # delete
        if trigger == "table" and active_cell and active_cell.get("column_id") == "_delete":
            row = table_data[active_cell["row"]]
            delete_record(PROJECT_ENDPOINT, row["Id"])

        # add project + link relations
        elif trigger == "btn_add":
            payload = {}
            if name:
                payload["name"] = name
            if date:
                payload["date"] = date
            if address:
                payload["address"] = address

            if not payload:
                return table_data, dash.no_update, " Заполните хотя бы одно поле."

            created = create_record(PROJECT_ENDPOINT, payload)
            project_id = created.get("Id", created.get("id"))

            if project_id is not None:
                if org_id is not None:
                    link_record(project_id, LINK_ORG, int(org_id))
                if dept_id is not None:
                    link_record(project_id, LINK_DEPT, int(dept_id))
                if user_id is not None:
                    link_record(project_id, LINK_USER, int(user_id))

        # save edits for simple fields
        elif trigger == "btn_save":
            for row in table_data:
                rid = row.get("Id")
                if rid is None:
                    continue
                payload = {"Id": int(rid)}
                for f in EDITABLE_FIELDS:
                    if f in row:
                        payload[f] = row.get(f)
                patch_record(PROJECT_ENDPOINT, payload)

        # refresh = just reload
        elif trigger == "btn_refresh":
            pass

        # reload data + chart
        org_df_new = fetch_df(ORG_ENDPOINT)  # чтобы названия организаций были актуальными
        projects_raw_new = fetch_df(PROJECT_ENDPOINT)
        table_df = prepare_projects(normalize_for_table(projects_raw_new))
        fig = make_projects_by_org_chart(projects_raw_new, org_df_new)

        return table_df.to_dict("records"), fig, " Готово"

    except Exception as e:
        return table_data, dash.no_update, f" Ошибка: {e}"


if __name__ == "__main__":
    app.run(debug=True)