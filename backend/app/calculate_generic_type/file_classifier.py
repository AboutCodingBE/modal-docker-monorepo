
#Extracted the functional part of https://github.com/hvanstappen/MODAL_textdatabase/blob/master/mime_to_genericType.py
class FileClassifier:
    """
    A class to classify files into generic types based on their MIME type or file extension.
    """

    def __init__(self):
        """
        Initializes the FileClassifier with predefined mappings for MIME types and extensions.
        """
        self.file_mimetype_map = {
            'text': 'tekstbestand',
            'multipart': 'tekstbestand',
            'audio': 'geluidsbestand',
            'application/x-dbf': 'gegevensbestand',
            'application/vnd.wordperfect; version=5.1' : 'tekstbestand',
            'application/vnd.wordperfect': 'tekstbestand',
            'application/vnd.wordperfect; version=5.0' : 'tekstbestand',
            'application/x-font-woff' : 'lettertypebestand',
            'application/octet-stream' : 'andere',
            'application/postscript': 'tekstbestand',
            'application/vnd.ms-excel': 'rekenbestand',
            'application/vnd.ms-powerpoint': 'presentatiebestand',
            'application/vnd.ms-word': 'tekstbestand',
            'application/msword' : 'tekstbestand',
            'application/msword2' : 'tekstbestand',
            'application/pdf': 'tekstbestand',
            'application/rtf': 'tekstbestand',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'presentatiebestand',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'rekenbestand',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'tekstbestand',
            'application/vnd.ms-excel.sheet.macroEnabled.12': 'rekenbestand',
            'application/x-fat-diskimage' : 'compressiebestand',
            'application/x-msdownload': 'andere',
            'application/x-msdownload; format=pe32': 'andere',
            'application/x-msdownload; format=pe': 'andere',
            'audio/mpeg' : 'geluidsbestand',
            'image' : 'beeldbestand',
            'application/pkcs7-signature' : 'andere',
            'application/vnd.iccprofile' : 'andere',
            'application/x-font-ttf' : 'lettertypebestand',
            'application/x-msaccess' : 'gegevensbestand',
            'application/x-mswrite' : 'tekstbestand',
            'application/x-font-printer-metric' : 'andere',
            'application/xml' : 'gegevensbestand',
            'application / vnd.ms - htmlhelp' : 'andere',
            'application/vnd.ms-cab-compressed' : 'compressiebestand',
            'application/inf' : 'andere',
            'video' : 'videobestand',
            'application/x-tika-msoffice' : 'tekstbestand',
            'application/vnd.ms-outlook' : 'berichtbestand',
            'application/x-bat' : 'andere',
            'application/coreldraw' : 'andere',
            'application/x-tika-msoffice-embedded; format=comp_obj' : 'andere',
            'application/x-font-type1' : 'lettertypebestand',
            'application/java-archive' : 'compressiebestand',
            'application/vnd.lotus-1-2-3; version=4' : 'rekenbestand',
            'application/vnd.ms-htmlhelp' : 'andere',
            'application/x-quattro-pro; version=6' : 'rekenbestand',
            'application/x-lha': 'compressiebestand',
            'application/vnd.ms-excel.sheet.binary.macroenabled.12' : 'rekenbestand',
            'application/x-font-otf' : 'lettertypebestand',
            'application/x-bplist-webarchive': 'compressiebestand',
            'application/x-stuffit' : 'compressiebestand',
            'application/x-mspublisher': 'tekstbestand',
            'application/vnd.apple.pages.18': 'tekstbestand',
            'application/vnd.openxmlformats-officedocument': 'tekstbestand',
            'application/vnd.ms-excel.sheet.macroenabled.12': 'rekenbestand',
            'application/vnd.apple.unknown.13': 'andere',
            'application/msword5': 'tekstbestand',
            'application / gzip': 'compressiebestand',
            'application/vnd.oasis.opendocument.text-master': 'tekstbestand',
            'application/zip': 'compressiebestand',
            'application/vnd.ms-word.document.macroenabled.12' : 'tekstbestand',
            'message/rfc822': 'berichtbestand',
            'application/gzip': 'compressiebestand',

            # General multipart, can be refined
        }
        self.extension_map = {
            # Tekstbestand
            '.doc': 'tekstbestand',
            '.docx': 'tekstbestand',
            '.odt': 'tekstbestand',
            '.pdf': 'tekstbestand',
            '.rtf': 'tekstbestand',
            '.txt': 'tekstbestand',
            '.wpd': 'tekstbestand',
            # Rekenbestand
            '.xls': 'rekenbestand',
            '.xlsx': 'rekenbestand',
            '.ods': 'rekenbestand',
            # Presentatiebestand
            '.ppt': 'presentatiebestand',
            '.pptx': 'presentatiebestand',
            '.key': 'presentatiebestand',
            '.odp': 'presentatiebestand',
            # Beeldbestand
            '.bmp': 'beeldbestand',
            '.gif': 'beeldbestand',
            '.psd': 'beeldbestand',
            '.tif': 'beeldbestand',
            '.tiff': 'beeldbestand',
            '.jpg': 'beeldbestand',
            '.jpeg': 'beeldbestand',
            '.png': 'beeldbestand',
            '.ps': 'beeldbestand',
            # Geluidsbestand
            '.mp3': 'geluidsbestand',
            '.ogg': 'geluidsbestand',
            '.wav': 'geluidsbestand',
            '.cda': 'geluidsbestand',
            # Videobestand
            '.mkv': 'videobestand',
            '.mov': 'videobestand',
            '.mp4': 'videobestand',
            '.avi': 'videobestand',
            '.mpg': 'videobestand',
            '.wmv': 'videobestand',
            # Berichtbestand
            '.eml': 'berichtbestand',
            '.msg': 'berichtbestand',
            '.pst': 'berichtbestand',
            # Compressiebestand
            '.zip': 'compressiebestand',
            '.rar': 'compressiebestand',
            '.tar.gz': 'compressiebestand',
            '.7z': 'compressiebestand',
            # Gegevensbestand
            '.sql': 'gegevensbestand',
            '.xml': 'gegevensbestand',
            '.csv': 'gegevensbestand',
            '.dat': 'gegevensbestand',
            '.mdb': 'gegevensbestand',
            'json': 'gegevensbestand',
        }


    def get_generic_type(self, file_name, file_mimetype):
        """
        Determines the generic type of a file.

        The method first checks the MIME type. If no specific mapping is found,
        it falls back to checking the file extension.

        Args:
            file_name (str): The name of the file (e.g., 'document.pdf').
            file_mimetype (str): The MIME type of the file (e.g., 'application/pdf').

        Returns:
            str: The determined generic file type, or 'onbekend' if not found.
        """
        if file_mimetype:
            # Check the primary type (e.g., 'text' in 'text/plain')
            primary_type = file_mimetype.split('/')[0].lower()
            if primary_type in self.file_mimetype_map:
                # Special handling for IANA multipart as per requirements
                if primary_type == 'multipart':
                     _, extension = os.path.splitext(file_name.lower())
                     if extension in ['.xls', '.xlsx', '.ods']:
                         return 'rekenbestand'
                return self.file_mimetype_map[primary_type]

            # Check the full MIME type (e.g., 'application/pdf')
            if file_mimetype.lower() in self.file_mimetype_map:
                return self.file_mimetype_map[file_mimetype.lower()]

        # Fallback to checking the file extension
        if file_name:
            # Handle double extensions like .tar.gz
            for ext in self.extension_map:
                if file_name.lower().endswith(ext):
                    return self.extension_map[ext]

        return 'onbekend'