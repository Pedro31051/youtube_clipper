import { fireEvent, render, screen } from "@testing-library/react";
import { Check } from "lucide-react";
import { describe, expect, it, vi } from "vitest";

import { Button, EmptyState, SkeletonCards, StatusBadge } from "./ui";

describe("UI-6 primitives", () => {
  it("exposes semantic async and status states", () => {
    render(
      <>
        <StatusBadge status="processing">Processando</StatusBadge>
        <SkeletonCards aria-label="Carregando candidatos" />
      </>
    );

    expect(screen.getByRole("status")).toHaveTextContent("Processando");
    expect(screen.getByLabelText("Carregando candidatos")).toHaveAttribute(
      "aria-busy",
      "true"
    );
  });

  it("keeps button behavior and busy state accessible", () => {
    const onClick = vi.fn();
    const { rerender } = render(
      <Button variant="primary" icon={Check} onClick={onClick}>
        Confirmar
      </Button>
    );

    fireEvent.click(screen.getByRole("button", { name: "Confirmar" }));
    expect(onClick).toHaveBeenCalledOnce();

    rerender(<Button busy>Confirmar</Button>);
    expect(screen.getByRole("button", { name: "Confirmar" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Confirmar" })).toHaveAttribute(
      "aria-busy",
      "true"
    );
  });

  it("renders a reusable empty state without decorative text", () => {
    render(
      <EmptyState
        title="Nada por aqui"
        description="Altere os filtros para continuar."
      />
    );

    expect(screen.getByRole("heading", { name: "Nada por aqui" })).toBeVisible();
    expect(screen.getByText("Altere os filtros para continuar.")).toBeVisible();
  });
});
