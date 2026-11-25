select
    p.product_id,
    p.product_category_name,
    coalesce(t.product_category_name_english, p.product_category_name, 'unknown') as category,
    p.product_name_lenght as product_name_length,
    p.product_description_lenght as product_description_length,
    p.product_photos_qty,
    p.product_weight_g,
    p.product_length_cm,
    p.product_height_cm,
    p.product_width_cm
from {{ source('raw', 'products') }} as p
left join {{ source('raw', 'product_category_name_translation') }} as t
    using (product_category_name)
