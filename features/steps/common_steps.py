"""Steps compartidos por todas las features."""
from behave import then


@then("the response status is {status_code:d}")
def step_response_status(context, status_code):
    assert context.response is not None, "No se ejecutó ninguna petición"
    assert context.response.status_code == status_code, (
        f"Se esperaba {status_code} y se obtuvo {context.response.status_code}: {context.response.text}"
    )
