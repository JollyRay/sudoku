from django import template

register = template.Library()

@register.filter(name="range")
def range_filter(value):
    return range(value)

@register.filter(name="range_sudoku")
def range_sudoku_filter(value):
    def temp_gen():
        for index in range(value):
            big_cell_index = index // 9
            big_cell_row_index = big_cell_index // 3
            cell_in_big_cell_index = index % 9
            row_in_big_cell_index = cell_in_big_cell_index // 3

            finish_index = (big_cell_index % 3 * 3) + big_cell_row_index * 27 + row_in_big_cell_index * 6 + cell_in_big_cell_index

            yield {
                'big_cell_number': big_cell_index + 1, 
                'cell_in_big_cell_index': cell_in_big_cell_index, 
                'finish_index': finish_index
            }

    return temp_gen()

