document.addEventListener('DOMContentLoaded', () => {
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    const processBtn = document.getElementById('processBtn');
    const spinner = document.getElementById('spinner');
    const customIgnores = document.getElementById('customIgnores');
    
    const resultCard = document.getElementById('resultCard');
    const statFiles = document.getElementById('statFiles');
    const statLines = document.getElementById('statLines');
    const statSize = document.getElementById('statSize');
    const previewCode = document.getElementById('previewCode');
    const previewInfo = document.getElementById('previewInfo');
    
    const copyBtn = document.getElementById('copyBtn');
    const downloadBtn = document.getElementById('downloadBtn');
    const toast = document.getElementById('toast');
    
    let currentFile = null;
    let bundledResultText = '';

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
        if (!file.name.toLowerCase().endsWith('.zip')) {
            alert('Please select a valid .zip file');
            return;
        }
        currentFile = file;
        const dropText = dropZone.querySelector('.drop-text');
        dropText.innerHTML = `Selected: <span class="highlight">${file.name}</span> (${formatBytes(file.size)})`;
        processBtn.disabled = false;
    }

    processBtn.addEventListener('click', async () => {
        if (!currentFile) return;

        processBtn.disabled = true;
        spinner.style.display = 'inline-block';
        const btnText = processBtn.querySelector('.btn-text');
        btnText.textContent = 'Processing...';

        const formData = new FormData();
        formData.append('file', currentFile);
        formData.append('custom_ignores', customIgnores.value);

        try {
            const response = await fetch('/api/bundle', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (data.success) {
                bundledResultText = data.text;
                statFiles.textContent = data.file_count.toLocaleString();
                statLines.textContent = data.total_lines.toLocaleString();
                statSize.textContent = formatBytes(data.total_bytes);

                previewCode.textContent = data.text;
                previewInfo.textContent = `${data.file_count} files bundled`;
                resultCard.style.display = 'flex';
                resultCard.scrollIntoView({ behavior: 'smooth' });
            } else {
                alert('Error: ' + (data.error || 'Failed to process file'));
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
        if (!bundledResultText) return;
        navigator.clipboard.writeText(bundledResultText).then(() => {
            showToast('Copied project_context.txt to clipboard!');
        }).catch(err => {
            alert('Failed to copy: ' + err);
        });
    });

    downloadBtn.addEventListener('click', () => {
        if (!bundledResultText) return;
        const blob = new Blob([bundledResultText], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'project_context.txt';
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
