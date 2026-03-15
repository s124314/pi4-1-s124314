from playwright.sync_api import Page, expect


def test_dash_page_loads(page: Page):
    page.goto("http://127.0.0.1:8050") # Открывает страницу Dash

    expect(page).to_have_title("Dash") # Проверяет заголовок вкладки браузера

    expect(page.get_by_text("Dashboard проектов")).to_be_visible() # Проверяет, что заголовок страницы виден
    expect(page.get_by_role("button", name="Обновить данные")).to_be_visible() # Проверяет, что есть кнопка

    graphs = page.locator(".js-plotly-plot") # Ищет графики Plotly на странице 
    expect(graphs).to_have_count(2)            # и проверяет, что их два.

    table = page.locator("table")
    expect(table.first).to_be_visible() # Проверяет, что таблица отображается.