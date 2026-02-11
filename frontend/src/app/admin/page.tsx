"use client";

import { PageHeader } from "@/components/layout/page-header";
import { UnmatchedTable } from "@/components/admin/unmatched-table";

export default function AdminPage() {
  return (
    <div>
      <PageHeader
        title="Product Admin"
        subtitle="Manage product matching and metadata. Merge singletons, edit products, and unlink store products."
      />
      <UnmatchedTable />
    </div>
  );
}
