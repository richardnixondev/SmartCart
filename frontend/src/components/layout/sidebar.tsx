"use client";

import { useState } from "react";
import { NavLink } from "./nav-link";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  BarChart3,
  Swords,
  TrendingUp,
  ShoppingCart,
  Settings,
  Menu,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/", icon: <BarChart3 className="h-4 w-4" />, label: "Overview" },
  { href: "/price-battle", icon: <Swords className="h-4 w-4" />, label: "Price Battle" },
  { href: "/product-history", icon: <TrendingUp className="h-4 w-4" />, label: "Product History" },
  { href: "/basket-compare", icon: <ShoppingCart className="h-4 w-4" />, label: "Basket Compare" },
  { href: "/admin", icon: <Settings className="h-4 w-4" />, label: "Product Admin" },
];

export function Sidebar() {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <>
      {/* Mobile toggle */}
      <Button
        variant="ghost"
        size="icon"
        className="fixed top-3 left-3 z-50 lg:hidden"
        onClick={() => setMobileOpen(!mobileOpen)}
      >
        {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
      </Button>

      {/* Overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r bg-background transition-transform duration-200 lg:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {/* Branding */}
        <div className="flex flex-col items-center gap-1 px-4 py-6">
          <ShoppingCart className="h-10 w-10 text-primary" />
          <h1 className="text-xl font-bold">SmartCart</h1>
          <p className="text-xs text-muted-foreground">
            Irish Grocery Price Tracker
          </p>
        </div>

        <Separator />

        {/* Navigation */}
        <nav className="flex flex-col gap-1 p-4">
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.href} href={item.href} icon={item.icon}>
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
    </>
  );
}
