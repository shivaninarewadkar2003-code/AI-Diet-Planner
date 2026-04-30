// Toggle between Login and Register forms
function toggleForm(formType) {
    // Get form elements
    const loginForm = document.getElementById('loginForm');
    const registerForm = document.getElementById('registerForm');
    const loginBtn = document.getElementById('loginToggleBtn');
    const registerBtn = document.getElementById('registerToggleBtn');
    const loginImage = document.getElementById('loginImage');
    const registerImage = document.getElementById('registerImage');
    
    if (formType === 'login') {
        // Show login form, hide register form
        loginForm.classList.add('active');
        registerForm.classList.remove('active');
        
        // Update active state of buttons
        loginBtn.classList.add('active');
        registerBtn.classList.remove('active');
        
        // Show login image, hide register image
        loginImage.classList.add('active');
        registerImage.classList.remove('active');
    } else {
        // Show register form, hide login form
        registerForm.classList.add('active');
        loginForm.classList.remove('active');
        
        // Update active state of buttons
        registerBtn.classList.add('active');
        loginBtn.classList.remove('active');
        
        // Show register image, hide login image
        registerImage.classList.add('active');
        loginImage.classList.remove('active');
    }
}

// Handle Login Form Submission
async function handleLogin(event) {
    event.preventDefault();
    
    const email = document.getElementById('loginEmail').value;
    const password = document.getElementById('loginPassword').value;
    
    const response = await fetch('/login', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email, password })
    });
    
    const data = await response.json();
    
    if (data.success) {
        // Redirect based on assessment status
        window.location.href = data.redirect;
    } else {
        // Show error message
        const errorDiv = document.getElementById('loginError');
        errorDiv.textContent = data.message;
        errorDiv.style.display = 'block';
        
        // Hide error after 3 seconds
        setTimeout(() => {
            errorDiv.style.display = 'none';
        }, 3000);
    }
}

// Handle Register Form Submission
async function handleRegister(event) {
    event.preventDefault();
    
    const name = document.getElementById('regName').value;
    const email = document.getElementById('regEmail').value;
    const password = document.getElementById('regPassword').value;
    
    const response = await fetch('/register', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ name, email, password })
    });
    
    const data = await response.json();
    
    if (data.success) {
        // Redirect to assessment page
        window.location.href = data.redirect;
    } else {
        // Show error message
        const errorDiv = document.getElementById('registerError');
        errorDiv.textContent = data.message;
        errorDiv.style.display = 'block';
        
        // Hide error after 3 seconds
        setTimeout(() => {
            errorDiv.style.display = 'none';
        }, 3000);
    }
}

// Form validation helpers
function validateEmail(email) {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
}

function validatePassword(password) {
    return password.length >= 6;
}

// Add input validation to forms
document.addEventListener('DOMContentLoaded', function() {
    // Add real-time validation for login form
    const loginEmail = document.getElementById('loginEmail');
    const loginPassword = document.getElementById('loginPassword');
    
    if (loginEmail) {
        loginEmail.addEventListener('input', function() {
            if (validateEmail(this.value)) {
                this.style.borderColor = '#4caf50';
            } else {
                this.style.borderColor = '#e0e0e0';
            }
        });
    }
    
    if (loginPassword) {
        loginPassword.addEventListener('input', function() {
            if (validatePassword(this.value)) {
                this.style.borderColor = '#4caf50';
            } else {
                this.style.borderColor = '#e0e0e0';
            }
        });
    }
});