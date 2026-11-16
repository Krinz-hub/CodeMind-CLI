const display = document.getElementById('display');

function appendToDisplay(input) {
    display.value += input;
}

function clearDisplay() {
    display.value = '';
}

function deleteLast() {
    display.value = display.value.slice(0, -1);
}

function calculateResult() {
    try {
        // Using eval for simplicity in this basic calculator example.
        // In a production environment, consider using a safer expression parser.
        display.value = eval(display.value);
    } catch (error) {
        display.value = 'Error';
    }
}
