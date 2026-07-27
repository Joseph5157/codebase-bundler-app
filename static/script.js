document.addEventListener('DOMContentLoaded', () => {
    const tabZip = document.getElementById('tabZip');
    const tabGithub = document.getElementById('tabGithub');
    const dropZone = document.getElementById('dropZone');
    const urlContainer = document.getElementById('urlContainer');
    const githubUrl = document.getElementById('githubUrl');
    const fileInput = document.getElementById('fileInput');

    const processBtn = document.getElementById('processBtn');
    const spinner = document.getElementById('spinner');
    const customIgnores = document.getElementById('customIgnores');
    
    const resultCard = document.getElementById('resultCard');
    const statFiles = document.getElementById('statFiles');
    const statLines = document.getElementById('statLines');
    const statTokens = document.getElementById('statTokens');
    const statSize = document.getElementById('statSize');
    const statRedacted = document.getElementById('statRedacted');

    const fmtMarkdown = document.getElementById('fmtMarkdown');
    const fmtXml = document.getElementById('fmtXml');

    const previewTitle = document.getElementById('previewTitle');
    const previewCode = document.getElementById('previewCode');
    const previewInfo = document.getElementById('previewInfo');
    
    const copyBtn = document.getElementById('copyBtn');
    const downloadBtn = document.getElementById('downloadBtn');
    const toast = document.getElementById('toast');
    
    let activeMode = 'zip'; // 'zip' or 'github'
    let currentFile = null;
    let mdResultText = '';
    let xmlResultText = '';
    let currentFormat = 'markdown'; // 'markdown' or 'xml'

    // Tab Switcher
    tabZip.addEventListener('click', () => {
        activeMode = 'zip';
        tabZip.classList.add('active');
        tabGithub.classList.remove('active');
        dropZone.style.display = 'block';
        urlContainer.style.display = 'none';
    });

    tabGithub.addEventListener('click', () => {
        activeMode = 'github';
        tabGithub.classList.add('active');
        tabZip.classList.remove('active');
        urlContainer.style.display = 'block';
        dropZone.style.display = 'none';
    });

    // Format Switcher
    fmtMarkdown.addEventListener('click', () => {
        currentFormat = 'markdown';
        fmtMarkdown.classList.add('active');
        fmtXml.classList.remove('active');
        previewTitle.textContent = 'Preview: project_context.txt (Markdown)';
        previewCode.textContent = mdResultText;
    });

    fmtXml.addEventListener('click', () => {
        currentFormat = 'xml';
        fmtXml.classList.add('active');
        fmtMarkdown.classList.remove('active');
        previewTitle.textContent = 'Preview: project_context.xml (XML)';
        previewCode.textContent = xmlResultText;
    });

    // Drag and Drop Events
    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.add('dragover');
        });
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.remove('dragover');
        });
    });

    dropZone.addEventListener('drop', (e) => {
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFileSelect(files[0]);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileSelect(e.target.files[0]);
        }
    });

    function handleFileSelect(file) {
        if (!file.name.toLowerCase().endswith('.zip')) {
            alert('Please select a valid .zip file');
            return;
        }
        currentFile = file;
        const dropText = dropZone.querySelector('.drop-text');
        dropText.innerHTML = `Selected: <span class="highlight">${file.name}</span> (${formatBytes(file.size)})`;
    }

    processBtn.addEventListener('click', async () => {
        if (activeMode === 'zip' && !currentFile) {
            alert('Please select or drop a .zip file first.');
            return;
        }
        if (activeMode === 'github' && !githubUrl.value.trim()) {
            alert('Please enter a valid GitHub repository URL.');
            return;
        }

        processBtn.disabled = true;
        spinner.style.display = 'inline-block';
        const btnText = processBtn.querySelector('.btn-text');
        btnText.textContent = 'Processing...';

        try {
            let data;
            if (activeMode === 'zip') {
                const formData = new FormData();
                formData.append('file', currentFile);
                formData.append('custom_ignores', customIgnores.value);

                const response = await fetch('/api/bundle', {
                    method: 'POST',
                    body: formData
                });
                data = await response.json();
            } else {
                const response = await fetch('/api/bundle-github', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        github_url: githubUrl.value.trim(),
                        custom_ignores: customIgnores.value.split(',').map(s => s.trim()).filter(Boolean)
                    })
                });
                data = await response.json();
            }

            if (data.success) {
                mdResultText = data.text;
                xmlResultText = data.xml_text || data.text;

                statFiles.textContent = data.file_count.toLocaleString();
                statLines.textContent = data.total_lines.toLocaleString();
                statTokens.textContent = `~${data.token_count.toLocaleString()}`;
                statSize.textContent = formatBytes(data.total_bytes);
                statRedacted.textContent = data.redacted_count.toLocaleString();

                previewCode.textContent = (currentFormat === 'xml') ? xmlResultText : mdResultText;
                previewInfo.textContent = `${data.file_count} files bundled`;
                resultCard.style.display = 'flex';
                resultCard.scrollIntoView({ behavior: 'smooth' });
            } else {
                alert('Error: ' + (data.error || 'Failed to process repository'));
            }
        } catch (err) {
            alert('Failed to connect to server: ' + err.message);
        } finally {
            processBtn.disabled = false;
            spinner.style.display = 'none';
            btnText.textContent = 'Generate Context';
        }
    });

    copyBtn.addEventListener('click', () => {
        const textToCopy = (currentFormat === 'xml') ? xmlResultText : mdResultText;
        if (!textToCopy) return;
        navigator.clipboard.writeText(textToCopy).then(() => {
            showToast(`Copied ${currentFormat.toUpperCase()} project context to clipboard!`);
        }).catch(err => {
            alert('Failed to copy: ' + err);
        });
    });

    downloadBtn.addEventListener('click', () => {
        const textToDownload = (currentFormat === 'xml') ? xmlResultText : mdResultText;
        if (!textToDownload) return;
        const ext = (currentFormat === 'xml') ? 'xml' : 'txt';
        const blob = new Blob([textToDownload], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `project_context.${ext}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    });

    function showToast(message) {
        toast.textContent = message;
        toast.classList.add('show');
        setTimeout(() => {
            toast.classList.remove('show');
        }, 3000);
    }

    function formatBytes(bytes, decimals = 2) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    }
});
