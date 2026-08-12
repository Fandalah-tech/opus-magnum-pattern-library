from .canonical import canonical_solution_hash, canonical_solution_payload
from .convergence import canonical_convergence_key, extract_convergence_motifs
from .diagnostics import analyze_solution
from .fragment_evidence import trace_fragment_evidence
from .fragment_flow import build_fragment_flow_graph
from .fragments import extract_solution_fragments, functional_role
from .graph import build_solution_graph
from .patterns import detect_patterns
from .portfolio import solution_architecture_signature, specialization_axes
from .puzzle_features import canonical_molecule_hash, puzzle_feature_fingerprint, puzzle_feature_payload
from .replay_glyphs import build_replay_trace, process_basic_glyphs
from .timeline import build_program_timeline

__all__ = [
    "analyze_solution",
    "build_fragment_flow_graph",
    "build_replay_trace",
    "build_solution_graph",
    "build_program_timeline",
    "canonical_convergence_key",
    "canonical_molecule_hash",
    "canonical_solution_hash",
    "canonical_solution_payload",
    "detect_patterns",
    "extract_convergence_motifs",
    "extract_solution_fragments",
    "functional_role",
    "process_basic_glyphs",
    "solution_architecture_signature",
    "specialization_axes",
    "puzzle_feature_fingerprint",
    "puzzle_feature_payload",
    "trace_fragment_evidence",
]
