import { notFound } from 'next/navigation';
import { getVariantById, VariantFullPage, VARIANTS } from '../_components/FootprintGallery';

export function generateStaticParams() {
  return VARIANTS.map((variant) => ({ variant: variant.id }));
}

export default async function VariantPage({ params }: { params: Promise<{ variant: string }> }) {
  const { variant } = await params;
  const found = getVariantById(variant);

  if (!found) {
    notFound();
  }

  return <VariantFullPage variant={found} />;
}
