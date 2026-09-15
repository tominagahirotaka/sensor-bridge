#!/usr/bin/env python3
"""Raw/processed sensor-bridge binary file I/O: a small pickled header
followed by the sensor's binary payload, shared by the .dat and .cpt files."""

import os
import pickle

from mylib.i18n import t

RAW_MAGIC = b'HS'
PROCESSED_MAGIC = b'HP'
SUPPORTED_MAGIC = {RAW_MAGIC, PROCESSED_MAGIC}


class FileIO:
    """Reads/writes the pickled header + binary payload used by .dat/.cpt files."""

    def make_header(self, p):
        """Serialize `p` (a communicate.Header) into a magic+length-prefixed blob."""
        pickled = pickle.dumps(p)
        magic_bytes = RAW_MAGIC
        header_len = len(pickled).to_bytes(2, 'big')
        return magic_bytes + header_len + pickled

    def _read_pickled_header(self, stream):
        magic = stream.read(2)
        if magic not in SUPPORTED_MAGIC:
            return (magic, None)
        header_size = int.from_bytes(stream.read(2), 'big')
        try:
            header = pickle.loads(stream.read(header_size))
        except TypeError as e:
            print("Error: ", e)
            print(t('fio.py38_incompat_1'))
            print(t('fio.py38_incompat_2'))
            print(t('fio.py38_incompat_3'))
            print(t('fio.py38_incompat_4'))
            print(t('fio.py38_incompat_5'))
            exit(0)
        return (magic, header)

    def write_open(self, p):
        dirname = p.env_set['dir_name']
        head_str = p.machine['node']
        format_time = "{:%Y%m%d_%H%M%S}".format(p.time['start_time'])
        os.makedirs(dirname, exist_ok=True)
        self.data_filename = f'{dirname}/{head_str}_{format_time}.dat'
        self.cpt_filename = f'{dirname}/{head_str}_{format_time}.cpt'
        # Pickle object p and write it at the start of the file
        self.fwrite = open(self.data_filename, 'wb')
        self.fwrite.write(self.make_header(p))
        print(t('fio.write_to', path=self.data_filename))

    def write_close_cpt(self, p):
        with open(self.cpt_filename, 'wb') as f:
            f.write(self.make_header(p))
        print(t('fio.write_to', path=self.cpt_filename))

    def read_open(self, filename):
        self.data_filename = os.path.splitext(filename)[0] + '.dat'
        self.cpt_filename = os.path.splitext(filename)[0] + '.cpt'
        self.fread = open(self.data_filename, 'rb')

        self.file_magic, header = self._read_pickled_header(self.fread)
        if header is not None:
            print(t('fio.read_from', path=self.data_filename))
        else:
            print(t('fio.no_header'))
            self.fread.close()
            self.fread = open(self.data_filename, 'rb')
            header = None
        # If a checkpoint file exists, load the header from it instead
        if os.path.exists(self.cpt_filename):
            with open(self.cpt_filename, 'rb') as f:
                _, checkpoint_header = self._read_pickled_header(f)
                if checkpoint_header is not None:
                    header = checkpoint_header
                    print(t('fio.read_from', path=self.cpt_filename))
                else:
                    print(t('fio.not_checkpoints_file', path=self.cpt_filename))
        return header
