"""
PTD Reader Experiment

Purpose
-------
This module is used only for reverse engineering the HP ALM PTD format.

A PTD file is a binary table export contained inside a QCP archive.

At this stage we do NOT try to parse the complete structure.
Our goal is simply to discover:

- how strings are stored
- where records begin/end
- how fields are separated
- how this relates to db_xmlmap.xml

Once the format is understood this module will be replaced
by the production PTD reader.
"""

from pathlib import Path


class PtdReaderExperiment:
    """
    Experimental reader used while reverse engineering PTD files.

    This is NOT the final parser.

    It extracts printable strings from a binary PTD file so that
    we can understand the internal storage format used by HP ALM.
    """

    def read_strings(
        self,
        file: str | Path,
        min_length: int = 3
    ) -> list[str]:
        """
        Extract printable strings from a PTD file.

        Parameters
        ----------
        file
            Path to the PTD file.

        min_length
            Ignore strings shorter than this value.

        Returns
        -------
        list[str]
            List of extracted strings.
        """

        # Read the complete binary file into memory.
        data = Path(file).read_bytes()

        strings = []

        # Temporary buffer used while building one string.
        current = bytearray()

        # Walk through every byte.
        for byte in data:

            # Keep only printable ASCII characters.
            if 32 <= byte <= 126:
                current.append(byte)

            else:

                # Binary byte found.
                # Finish current string.
                if len(current) >= min_length:
                    strings.append(
                        current.decode("latin1")
                    )

                current = bytearray()

        # File may end without a separator.
        if len(current) >= min_length:
            strings.append(
                current.decode("latin1")
            )

        return strings