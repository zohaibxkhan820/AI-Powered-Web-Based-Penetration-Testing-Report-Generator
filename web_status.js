const https = require('https');
const http = require('http');
const readline = require('readline');

// Create readline interface for terminal input
const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
});

// Function to validate URL
function isValidUrl(url) {
    const urlPattern = /^(https?:\/\/)?([\w.-]+)\.([a-z]{2,})(\/.*)?$/i;
    return urlPattern.test(url);
}

// Function to check website accessibility
function checkWebsiteStatus(url, callback) {
    // Clean and validate URL
    let cleanUrl = url.replace(/^https?:\/\//, '').replace(/\/+$/, '');
    if (!isValidUrl(cleanUrl)) {
        console.log('Invalid URL format. Please enter a valid URL (e.g., example.com)');
        callback(false);
        return;
    }

    const protocols = ['https', 'http'];
    let attempts = 0;

    function tryProtocol(protocolIndex) {
        if (protocolIndex >= protocols.length) {
            console.log(`Website ${url} is not accessible on either http or https`);
            callback(false);
            return;
        }

        const protocol = protocols[protocolIndex];
        const testUrl = `${protocol}://${cleanUrl}`;
        console.log(`Checking status for ${testUrl}...`);

        const client = protocol === 'https' ? https : http;
        const req = client.request(testUrl, { method: 'HEAD', timeout: 5000 }, (res) => {
            if (res.statusCode >= 200 && res.statusCode < 300) {
                console.log(`Website ${testUrl} is accessible (Status: ${res.statusCode})`);
                callback(true);
            } else {
                console.log(`Website ${testUrl} server is down (Status: ${res.statusCode})`);
                tryProtocol(protocolIndex + 1);
            }
        });

        req.on('error', (error) => {
            let errorMessage;
            if (error.code === 'ENOTFOUND') {
                errorMessage = 'DNS lookup failed (website not found)';
            } else if (error.code === 'ECONNREFUSED') {
                errorMessage = 'Connection refused';
            } else {
                errorMessage = error.message;
            }
            console.log(`Website ${testUrl} server is down: ${errorMessage}`);
            tryProtocol(protocolIndex + 1);
        });

        req.on('timeout', () => {
            req.destroy();
            console.log(`Website ${testUrl} server is down: Request timed out`);
            tryProtocol(protocolIndex + 1);
        });

        req.end();
    }

    tryProtocol(0);
}

// Function to prompt for URL and check status
function promptForUrl() {
    rl.question('Enter website URL (e.g., example.com): ', (url) => {
        if (!url.trim()) {
            console.log('Please enter a valid URL');
            promptForUrl();
            return;
        }

        checkWebsiteStatus(url, (success) => {
            rl.question('Check another website? (y/n): ', (answer) => {
                if (answer.toLowerCase() === 'y') {
                    promptForUrl();
                } else {
                    console.log('Exiting...');
                    rl.close();
                }
            });
        });
    });
}

// Start the script
console.log('Website Status Checker');
promptForUrl();