# PDF Reader - Lightweight PDF Signature Validator

A simple, lightweight PDF reader and signature validator that works offline and doesn't require heavy dependencies.

## Features

- Open and read PDF files
- Validate digital signatures (PKCS#7 / CMS)
- Display signer information and validation results
- Cross-platform support (Windows, Linux, macOS)
- Offline capable
- Lightweight web-based UI
- No heavy frameworks required

## Requirements

- Python 3.7 or higher
- Dependencies listed in `requirements.txt`

## Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/pdf-reader.git
cd pdf-reader
```

2. Create a virtual environment (recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

1. Start the application:
```bash
python pdf_reader.py
```

2. Open your web browser and navigate to:
```
http://localhost:5000
```

3. Use the web interface to:
   - Drag and drop PDF files
   - View document information
   - Check digital signatures
   - Validate signature authenticity

## Building a Standalone Executable

To create a standalone executable:

1. Install PyInstaller:
```bash
pip install pyinstaller
```

2. Create the executable:
```bash
pyinstaller --onefile --add-data "templates;templates" pdf_reader.py
```

The executable will be created in the `dist` directory.

## Security Notes

- The application runs locally and doesn't send any data to external servers
- All PDF processing is done offline
- Temporary files are automatically cleaned up after processing

## License

This project is open source and available under the MIT License.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. 