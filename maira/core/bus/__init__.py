"""In-process event bus for decoupled inter-module communication.

Modules publish domain events and subscribe to topics without direct
imports. The bus is the only sanctioned cross-module runtime coupling.
"""
