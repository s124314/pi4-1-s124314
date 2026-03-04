import requests
import pandas as pd
from dash import Dash, html, dash_table, dcc
from dash.dependencies import Input, Output
import plotly.express as px

# settings

NOCODB_URL = "http://localhost:8080"
TOKEN = "9wVU4w2M3YUYhxIHf1ZHSH4-CXbOqQKRo4YzZPdW"

PROJECT_ENDPOINT = "/api/v2/tables/mqejgb1k2tepfze/records"
ORG_ENDPOINT     = "/api/v2/tables/mjd7jczb07m6a92/records"
USER_ENDPOINT    = "/api/v2/tables/mbsjp5zwx90vd54/records"

COL_ORG = "Orgatisation"
COL_USER = "user"

# -------

def headers():
    return {"xc-token": TOKEN}


def fetch_df(endpoint):

    url = f"{NOCODB_URL}{endpoint}?limit=1000"

    r = requests.get(url, headers=headers())
    r.raise_for_status()

    data = r.json()
    rows = data.get("list", data)

    return pd.DataFrame(rows)


def extract_ids(value):

    if value is None:
        return []

    if isinstance(value, int):
        return [value]

    if isinstance(value, float):
        return [int(value)]

    if isinstance(value, str):

        parts = value.split(",")

        ids = []
        for p in parts:
            try:
                ids.append(int(p.strip()))
            except:
                pass

        return ids

    if isinstance(value, dict):

        if "Id" in value:
            return [value["Id"]]

        return []

    if isinstance(value, list):

        ids = []
        for item in value:
            ids.extend(extract_ids(item))

        return ids

    return []


def normalize_df(df):

    def to_cell_value(x):

        if x is None:
            return None

        if isinstance(x, (str, int, float, bool)):
            return x

        if isinstance(x, list):

            values = []

            for item in x:

                if isinstance(item, dict):

                    if "Id" in item:
                        values.append(str(item["Id"]))

                    elif "name" in item:
                        values.append(item["name"])

                    else:
                        values.append(str(item))

                else:
                    values.append(str(item))

            return ", ".join(values)

        if isinstance(x, dict):

            for key in ["Id", "name"]:
                if key in x:
                    return str(x[key])

            return str(x)

        return str(x)

    df = df.copy()

    for col in df.columns:

        if df[col].apply(lambda v: isinstance(v, (dict, list))).any():
            df[col] = df[col].apply(to_cell_value)

    return df


def id_to_name_map(df):

    if df.empty:
        return {}

    name_col = "name" if "name" in df.columns else df.columns[1]

    return dict(zip(df["Id"], df[name_col]))


# графики 

def chart_projects_by_org(projects_df, org_df):

    if COL_ORG not in projects_df.columns:
        return {}

    org_map = id_to_name_map(org_df)

    rows = []

    for _, r in projects_df.iterrows():

        org_ids = extract_ids(r[COL_ORG])

        for oid in org_ids:
            rows.append({"org": oid})

    if not rows:
        return {}

    tmp = pd.DataFrame(rows)

    counts = tmp.groupby("org").size().reset_index(name="projects")

    counts["organisation"] = counts["org"].map(org_map)

    return px.bar(
        counts,
        x="organisation",
        y="projects",
        title="Количество проектов по организациям"
    )


def chart_projects_by_user(projects_df, user_df):

    if COL_USER not in projects_df.columns:
        return {}

    user_map = id_to_name_map(user_df)

    rows = []

    for _, r in projects_df.iterrows():

        user_ids = extract_ids(r[COL_USER])

        for uid in user_ids:
            rows.append({"user": uid})

    if not rows:
        return {}

    tmp = pd.DataFrame(rows)

    counts = tmp.groupby("user").size().reset_index(name="projects")

    counts["username"] = counts["user"].map(user_map)

    return px.bar(
        counts,
        x="username",
        y="projects",
        title="Количество проектов по пользователям"
    )


# загрузка данных 

projects_raw = fetch_df(PROJECT_ENDPOINT)
org_df = fetch_df(ORG_ENDPOINT)
user_df = fetch_df(USER_ENDPOINT)

table_df = normalize_df(projects_raw)


app = Dash(__name__)

app.layout = html.Div(

    style={"fontFamily": "Arial", "padding": "20px"},

    children=[

        html.H2("Dashboard проектов"),

        html.Button("Обновить данные", id="refresh"),

        dcc.Graph(
            id="chart_org",
            figure=chart_projects_by_org(projects_raw, org_df)
        ),

        dcc.Graph(
            id="chart_user",
            figure=chart_projects_by_user(projects_raw, user_df)
        ),

        dash_table.DataTable(

            id="table",

            data=table_df.to_dict("records"),

            columns=[{"name": c, "id": c} for c in table_df.columns],

            page_size=10,

            filter_action="native",
            sort_action="native",

            style_table={"overflowX": "auto"},
        ),
    ],
)


@app.callback(

    Output("table", "data"),
    Output("chart_org", "figure"),
    Output("chart_user", "figure"),

    Input("refresh", "n_clicks"),

)

def refresh_data(_):

    projects = fetch_df(PROJECT_ENDPOINT)
    org_df = fetch_df(ORG_ENDPOINT)
    user_df = fetch_df(USER_ENDPOINT)

    table = normalize_df(projects)

    chart1 = chart_projects_by_org(projects, org_df)
    chart2 = chart_projects_by_user(projects, user_df)

    return table.to_dict("records"), chart1, chart2


if __name__ == "__main__":
    app.run(debug=True)