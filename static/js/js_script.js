// Page navigation
const navButtons = document.querySelectorAll('.nav-button');
const pages = document.querySelectorAll('.page-content');

navButtons.forEach(button => {
    button.addEventListener('click', () => {
        const pageName = button.getAttribute('data-page');
        
        // Update active nav button
        navButtons.forEach(btn => btn.classList.remove('active'));
        button.classList.add('active');
        
        // Show corresponding page
        pages.forEach(page => page.classList.remove('active'));
        document.getElementById(`${pageName}-page`).classList.add('active');
        
        // Load data for the page
        if (pageName === 'questions') {
            loadQuestions('profed');
        } else if (pageName === 'takers') {
            loadTakers();
        } else if (pageName === 'attempts') {
            loadAttempts();
        }
    });
});

// Tab navigation
const tabButtons = document.querySelectorAll('.tab-button');
const tabPanes = document.querySelectorAll('.tab-pane');

tabButtons.forEach(button => {
    button.addEventListener('click', () => {
        const tabName = button.getAttribute('data-tab');
        
        // Update active tab button
        tabButtons.forEach(btn => btn.classList.remove('active'));
        button.classList.add('active');
        
        // Show corresponding tab pane
        tabPanes.forEach(pane => pane.classList.remove('active'));
        document.getElementById(`${tabName}-tab`).classList.add('active');
        
        // Load questions for this category
        loadQuestions(tabName);
    });
});

// Load Questions
async function loadQuestions(category) {
    try {
        const response = await fetch(`/api/questions/${category}`);
        const questions = await response.json();
        const list = document.getElementById(`${category}-list`);
        
        list.innerHTML = '';
        questions.forEach((question, index) => {
            const li = document.createElement('li');
            li.textContent = question;
            li.dataset.index = index;
            li.addEventListener('click', () => selectItem(li));
            list.appendChild(li);
        });
    } catch (error) {
        console.error('Error loading questions:', error);
    }
}

// Load Takers
async function loadTakers(search = '') {
    try {
        const response = await fetch(`/api/takers?search=${encodeURIComponent(search)}`);
        const takers = await response.json();
        const list = document.getElementById('takers-list');
        
        list.innerHTML = '';
        takers.forEach(taker => {
            const li = document.createElement('li');
            li.textContent = `${taker.name} - ${taker.email}`;
            li.dataset.id = taker.id;
            li.addEventListener('click', () => selectItem(li));
            list.appendChild(li);
        });
    } catch (error) {
        console.error('Error loading takers:', error);
    }
}

// Load Attempts
async function loadAttempts(search = '') {
    try {
        const response = await fetch(`/api/attempts?search=${encodeURIComponent(search)}`);
        const attempts = await response.json();
        const list = document.getElementById('attempts-list');
        
        list.innerHTML = '';
        attempts.forEach(attempt => {
            const li = document.createElement('li');
            li.textContent = `${attempt.taker} - Score: ${attempt.score} - Date: ${attempt.date}`;
            li.dataset.id = attempt.id;
            li.addEventListener('click', () => selectItem(li));
            list.appendChild(li);
        });
    } catch (error) {
        console.error('Error loading attempts:', error);
    }
}

// Search functions
function searchTakers() {
    const search = document.getElementById('takers-search').value;
    loadTakers(search);
}

function searchAttempts() {
    const search = document.getElementById('attempts-search').value;
    loadAttempts(search);
}

// Enter key support for search
document.getElementById('takers-search')?.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') searchTakers();
});

document.getElementById('attempts-search')?.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') searchAttempts();
});

// Select item
function selectItem(element) {
    const siblings = element.parentElement.querySelectorAll('li');
    siblings.forEach(li => li.classList.remove('selected'));
    element.classList.add('selected');
}

// Delete item
async function deleteItem(category) {
    const list = document.getElementById(`${category}-list`);
    const selected = list.querySelector('.selected');
    
    if (!selected) {
        alert('Please select an item to delete');
        return;
    }
    
    const index = selected.dataset.index;
    
    try {
        const response = await fetch(`/api/questions/${category}/${index}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            loadQuestions(category);
            alert('Item deleted successfully');
        } else {
            alert('Failed to delete item');
        }
    } catch (error) {
        console.error('Error deleting item:', error);
        alert('Error deleting item');
    }
}

// Upload file
function uploadFile(category) {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json,.txt,.csv';
    
    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            const response = await fetch(`/api/questions/${category}`, {
                method: 'POST',
                body: formData
            });
            
            if (response.ok) {
                loadQuestions(category);
                alert('File uploaded successfully');
            } else {
                alert('Failed to upload file');
            }
        } catch (error) {
            console.error('Error uploading file:', error);
            alert('Error uploading file');
        }
    };
    
    input.click();
}

// Quit function
function handleQuit() {
    if (confirm('Are you sure you want to quit?')) {
        window.location.href = '/logout';
    }
}

// Initialize - Load takers by default
document.addEventListener('DOMContentLoaded', () => {
    loadTakers();
});
