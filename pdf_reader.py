import os
import fitz  # PyMuPDF
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa, ec
from cryptography.hazmat.primitives.serialization import load_der_public_key, load_pem_public_key
from cryptography.hazmat.primitives import serialization
from OpenSSL import crypto
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory, url_for
import json
from datetime import datetime
import base64
import io
import hashlib
import uuid
import shutil

app = Flask(__name__, static_folder='static')

# Ensure temp directory exists
TEMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp')
os.makedirs(TEMP_DIR, exist_ok=True)

class PDFReader:
    def __init__(self, pdf_path=None):
        self.pdf_path = pdf_path
        self.doc = None
        self.signatures = []
        self.current_page = 0
        self.zoom = 1.0
        self.signature_fields = []
        
        if pdf_path and os.path.exists(pdf_path):
            try:
                self.doc = fitz.open(pdf_path)
            except Exception as e:
                print(f"Error opening PDF: {str(e)}")
                raise
        else:
            self.doc = fitz.open()

    def create_new_document(self, title, page_size='a4', orientation='portrait'):
        """Create a new blank PDF document."""
        try:
            # Close existing document if any
            if self.doc:
                self.doc.close()

            self.doc = fitz.open()
            
            # Set page dimensions
            if page_size == 'a4':
                width, height = fitz.paper_size('a4')
            elif page_size == 'letter':
                width, height = fitz.paper_size('letter')
            elif page_size == 'legal':
                width, height = fitz.paper_size('legal')
            else:
                width, height = fitz.paper_size('a4')

            if orientation == 'landscape':
                width, height = height, width

            # Create a new page
            page = self.doc.new_page(width=width, height=height)
            
            # Add a title to the page
            font_size = 12
            title_text = f"Document: {title}"
            page.insert_text((50, 50), title_text, fontsize=font_size)
            
            # Set document metadata
            self.doc.set_metadata({
                'title': title,
                'creator': 'PDF Reader X',
                'producer': 'PDF Reader X',
                'creationDate': fitz.get_pdf_now(),
                'modDate': fitz.get_pdf_now()
            })

            print(f"Document created with dimensions: {width}x{height}")
            return True
        except Exception as e:
            print(f"Error creating document: {str(e)}")
            return False

    def get_page_count(self):
        """Get the total number of pages in the document."""
        try:
            return len(self.doc) if self.doc else 0
        except Exception as e:
            print(f"Error getting page count: {str(e)}")
            return 0

    def get_page(self, page_num, zoom=1.0):
        """Get a specific page as an image."""
        try:
            if self.doc and 0 <= page_num < len(self.doc):
                page = self.doc[page_num]
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("png")
                return base64.b64encode(img_data).decode()
            return None
        except Exception as e:
            print(f"Error getting page: {str(e)}")
            return None

    def extract_signatures(self):
        """Extract signatures from the PDF document."""
        self.signatures = []
        
        try:
            if not self.doc:
                return self.signatures

            # Check for signature fields
            for page_num in range(len(self.doc)):
                page = self.doc[page_num]
                
                # Check form fields
                for widget in page.widgets():
                    if widget.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                        sig_info = {
                            'page': page_num + 1,
                            'rect': list(widget.rect),
                            'field_name': widget.field_name,
                            'type': 'Digital Signature Field',
                            'content': widget.field_value or 'Digital Signature',
                            'location': f"Page {page_num + 1}"
                        }
                        self.signatures.append(sig_info)

            # Check document catalog
            if self.doc.is_pdf:
                try:
                    pdf = self.doc.pdf_catalog()
                    if isinstance(pdf, dict):
                        acro_form = pdf.get('AcroForm', {})
                        if isinstance(acro_form, dict):
                            fields = acro_form.get('Fields', [])
                            for field in fields:
                                if isinstance(field, dict) and field.get('FT') == 'Sig':
                                    sig_info = {
                                        'page': 'Document Level',
                                        'type': 'Form Signature Field',
                                        'content': field.get('T', 'Digital Signature'),
                                        'location': 'Document Level'
                                    }
                                    self.signatures.append(sig_info)
                except Exception as e:
                    print(f"Error checking catalog signatures: {str(e)}")

            # Check for signature dictionaries
            try:
                for xref in range(1, self.doc.xref_length()):
                    try:
                        obj = self.doc.xref_object(xref)
                        if isinstance(obj, dict):
                            if obj.get('Type') == 'Sig' or obj.get('FT') == 'Sig':
                                sig_info = {
                                    'page': 'Document Level',
                                    'type': 'Signature Dictionary',
                                    'content': obj.get('Name', 'Digital Signature'),
                                    'location': 'Document Level',
                                    'date': obj.get('M', ''),
                                    'reason': obj.get('Reason', ''),
                                    'signer': obj.get('Name', '')
                                }
                                self.signatures.append(sig_info)
                    except:
                        continue
            except Exception as e:
                print(f"Error checking signature dictionaries: {str(e)}")

        except Exception as e:
            print(f"Error extracting signatures: {str(e)}")

        return self.signatures

    def add_signature_field(self, field_type, x, y, page_num):
        """Add a signature field to the document."""
        try:
            if not self.doc or not (0 <= page_num < len(self.doc)):
                return False

            page = self.doc[page_num]
            
            # Convert coordinates to PDF space
            rect = fitz.Rect(x, y, x + 150, y + 50)  # Default size for signature fields
            
            field_name = f"{field_type}_{len(self.signature_fields)}_{uuid.uuid4().hex[:8]}"
            
            if field_type == 'signature':
                widget = page.add_form_field(
                    name=field_name,
                    field_type=fitz.PDF_WIDGET_TYPE_SIGNATURE,
                    fill_color=fitz.utils.getColor('white'),
                    border_color=fitz.utils.getColor('black'),
                    rect=rect
                )
            elif field_type == 'initial':
                widget = page.add_form_field(
                    name=field_name,
                    field_type=fitz.PDF_WIDGET_TYPE_SIGNATURE,
                    fill_color=fitz.utils.getColor('white'),
                    border_color=fitz.utils.getColor('black'),
                    rect=fitz.Rect(x, y, x + 50, y + 30)  # Smaller size for initials
                )
            elif field_type in ['date', 'text']:
                widget = page.add_form_field(
                    name=field_name,
                    field_type=fitz.PDF_WIDGET_TYPE_TEXT,
                    fill_color=fitz.utils.getColor('white'),
                    border_color=fitz.utils.getColor('black'),
                    rect=rect
                )

            if widget:
                widget.update()
                self.signature_fields.append({
                    'type': field_type,
                    'page': page_num,
                    'rect': rect,
                    'name': field_name
                })
                return True
            return False
        except Exception as e:
            print(f"Error adding signature field: {str(e)}")
            return False

    def get_document_info(self):
        """Get comprehensive document information."""
        try:
            if not self.doc:
                return {
                    'filename': os.path.basename(self.pdf_path) if self.pdf_path else 'New Document',
                    'page_count': 0,
                    'title': '',
                    'author': '',
                    'subject': '',
                    'keywords': '',
                    'creator': 'PDF Reader X',
                    'producer': 'PDF Reader X',
                    'creation_date': '',
                    'modification_date': '',
                    'file_size': 0,
                    'encrypted': False,
                    'permissions': {
                        'print': True,
                        'copy': True,
                        'edit': True,
                        'annotate': True
                    }
                }

            info = {
                'filename': os.path.basename(self.pdf_path) if self.pdf_path else 'New Document',
                'page_count': len(self.doc),
                'title': self.doc.metadata.get('title', ''),
                'author': self.doc.metadata.get('author', ''),
                'subject': self.doc.metadata.get('subject', ''),
                'keywords': self.doc.metadata.get('keywords', ''),
                'creator': self.doc.metadata.get('creator', 'PDF Reader X'),
                'producer': self.doc.metadata.get('producer', 'PDF Reader X'),
                'creation_date': self.doc.metadata.get('creationDate', ''),
                'modification_date': self.doc.metadata.get('modDate', ''),
                'file_size': os.path.getsize(self.pdf_path) if self.pdf_path else 0,
                'encrypted': self.doc.is_encrypted,
                'permissions': {
                    'print': bool(self.doc.permissions & 4),
                    'copy': bool(self.doc.permissions & 16),
                    'edit': bool(self.doc.permissions & 8),
                    'annotate': bool(self.doc.permissions & 32)
                }
            }
            return info
        except Exception as e:
            print(f"Error getting document info: {str(e)}")
            return None

    def save_document(self, output_path=None):
        """Save the document to a file."""
        try:
            if not self.doc:
                print("No document to save")
                return None
                
            save_path = output_path or self.pdf_path
            if not save_path:
                save_path = os.path.join(TEMP_DIR, f"document_{uuid.uuid4().hex[:8]}.pdf")
            
            print(f"Saving document to: {save_path}")
            
            # Ensure the directory exists
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            
            # Save with proper options
            self.doc.save(
                save_path,
                incremental=False,  # Changed to False to ensure complete save
                encryption=fitz.PDF_ENCRYPT_NONE,  # Changed to NONE to avoid encryption issues
                clean=True,
                deflate=True,
                garbage=4
            )
            
            # Verify the file was created
            if not os.path.exists(save_path):
                raise Exception("File was not created after save")
            
            # Verify the file is readable
            try:
                test_doc = fitz.open(save_path)
                test_doc.close()
            except Exception as e:
                raise Exception(f"Saved file is not readable: {str(e)}")
            
            return save_path
        except Exception as e:
            print(f"Error saving document: {str(e)}")
            return None

    def close(self):
        """Close the PDF document."""
        try:
            if self.doc:
                self.doc.close()
                self.doc = None
        except Exception as e:
            print(f"Error closing document: {str(e)}")

# Global dictionary to store active PDF sessions
active_sessions = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'File must be a PDF'}), 400

        # Create a unique filename
        filename = f"upload_{uuid.uuid4().hex[:8]}_{file.filename}"
        temp_path = os.path.join(TEMP_DIR, filename)
        
        # Save the file
        file.save(temp_path)

        try:
            # Create a new session
            reader = PDFReader(temp_path)
            session_id = str(uuid.uuid4())
            active_sessions[session_id] = {
                'reader': reader,
                'path': temp_path
            }

            # Get initial document info
            doc_info = reader.get_document_info()
            signatures = reader.extract_signatures()
            first_page = reader.get_page(0)

            if first_page is None:
                raise Exception("Failed to render first page")

            return jsonify({
                'session_id': session_id,
                'document_info': doc_info,
                'signatures': signatures,
                'page_count': reader.get_page_count(),
                'first_page': first_page
            })
        except Exception as e:
            # Clean up on error
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/create_document', methods=['POST'])
def create_document():
    try:
        data = request.get_json()
        title = data.get('title', 'Untitled Document')
        page_size = data.get('pageSize', 'a4')
        orientation = data.get('orientation', 'portrait')

        # Create a new PDF reader instance
        reader = PDFReader()
        if not reader.create_new_document(title, page_size, orientation):
            raise Exception("Failed to create new document")

        # Save the document
        temp_path = os.path.join(TEMP_DIR, f"{title.replace(' ', '_')}_{uuid.uuid4().hex[:8]}.pdf")
        if not reader.save_document(temp_path):
            raise Exception("Failed to save document")

        # Create a new session
        session_id = str(uuid.uuid4())
        active_sessions[session_id] = {
            'reader': reader,
            'path': temp_path
        }

        # Get initial document info
        doc_info = reader.get_document_info()
        first_page = reader.get_page(0)

        if first_page is None:
            raise Exception("Failed to render first page")

        return jsonify({
            'session_id': session_id,
            'document_info': doc_info,
            'signatures': [],
            'page_count': reader.get_page_count(),
            'first_page': first_page
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/page/<session_id>/<int:page_num>')
def get_page(session_id, page_num):
    try:
        if session_id not in active_sessions:
            return jsonify({'error': 'Invalid session'}), 400

        reader = active_sessions[session_id]['reader']
        zoom = float(request.args.get('zoom', 1.0))
        
        page_data = reader.get_page(page_num, zoom)
        if page_data:
            return jsonify({'page_data': page_data})
        return jsonify({'error': 'Invalid page number'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/add_signature_field', methods=['POST'])
def add_signature_field():
    try:
        data = request.get_json()
        session_id = data.get('sessionId')
        field_type = data.get('type')
        x = data.get('x')
        y = data.get('y')
        page = data.get('page', 0)

        if session_id not in active_sessions:
            return jsonify({'error': 'Invalid session'}), 400

        reader = active_sessions[session_id]['reader']
        if reader.add_signature_field(field_type, x, y, page):
            # Save the document
            reader.save_document()
            # Return the updated page
            return jsonify({
                'success': True,
                'page_data': reader.get_page(page)
            })
        return jsonify({'error': 'Failed to add signature field'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/cleanup/<session_id>')
def cleanup_session(session_id):
    try:
        if session_id in active_sessions:
            session = active_sessions[session_id]
            if session['reader']:
                session['reader'].close()
            if os.path.exists(session['path']):
                os.remove(session['path'])
            del active_sessions[session_id]
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(app.static_folder, filename)

@app.route('/save/<session_id>', methods=['POST'])
def save_document(session_id):
    try:
        if session_id not in active_sessions:
            return jsonify({'error': 'Invalid session'}), 400

        session = active_sessions[session_id]
        reader = session['reader']
        
        if not reader or not reader.doc:
            return jsonify({'error': 'No document loaded'}), 400

        # Get the current document path
        current_path = session['path']
        
        try:
            # Save the document
            saved_path = reader.save_document(current_path)
            if not saved_path:
                raise Exception("Failed to save document")

            return jsonify({
                'success': True,
                'message': 'Document saved successfully',
                'path': saved_path
            })
        except Exception as e:
            print(f"Error during save operation: {str(e)}")
            raise e

    except Exception as e:
        print(f"Error saving document: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Cleanup temporary files on startup
def cleanup_temp_files():
    try:
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR)
        os.makedirs(TEMP_DIR)
    except Exception as e:
        print(f"Error cleaning up temp files: {str(e)}")

if __name__ == '__main__':
    cleanup_temp_files()
    app.run(debug=True, port=5000) 