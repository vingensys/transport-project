# transport/letters/__init__.py

from transport.letters.signatories import (
    get_active_letter_signatories,
    get_signatory_by_id,
    signature_lines,
)

from transport.letters.snapshots import (
    build_snapshot,
    build_canonical_snapshot_for_placement,
    hash_canonical_snapshot,
    booking_requires_attachment_pdf,
)

from transport.letters.storage import (
    booking_letters_dir,
    next_letter_sequence,
    merge_pdfs,
)

from transport.letters.pdf_placement import generate_placement_advice_pdf
from transport.letters.pdf_modification import generate_modification_advice_pdf
