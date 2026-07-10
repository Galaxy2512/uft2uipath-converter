from pathlib import Path


class PtdExplorer:

    def inspect(self, file: str | Path, bytes_to_read: int = 512):

        path = Path(file)

        with open(path, "rb") as f:
            data = f.read(bytes_to_read)

        print("=" * 80)
        print(path.name)
        print("=" * 80)

        print("\nHEX:\n")

        for i in range(0, len(data), 16):

            chunk = data[i:i + 16]

            hex_values = " ".join(f"{b:02X}" for b in chunk)

            ascii_values = "".join(
                chr(b) if 32 <= b < 127 else "."
                for b in chunk
            )

            print(f"{i:08X}  {hex_values:<48} {ascii_values}")

        print("\nTEXT:\n")

        try:
            print(data.decode("latin1"))
        except Exception:
            print("Cannot decode")