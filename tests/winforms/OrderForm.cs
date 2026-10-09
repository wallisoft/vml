using System;
using System.Windows.Forms;

namespace Shop
{
    public partial class OrderForm : Form
    {
        private decimal total;

        public OrderForm()
        {
            InitializeComponent();
        }

        private void OrderForm_Load(object sender, EventArgs e)
        {
            cmbSize.SelectedIndex = 0;
        }

        private void btnSave_Click(object sender, EventArgs e)
        {
            if (txtCustomer.Text == "")
            {
                MessageBox.Show("Who is it for?");
                return;
            }
            Close();
        }

        private void txtCustomer_TextChanged(object sender, EventArgs e)
        {
            btnSave.Enabled = txtCustomer.Text.Length > 0;
        }

        private void newItem_Click(object sender, EventArgs e)
        {
            txtCustomer.Clear();
        }

        private void grid_CellDoubleClick(object sender, DataGridViewCellEventArgs e)
        {
            MessageBox.Show(grid.Rows[e.RowIndex].Cells[0].Value.ToString());
        }

        private decimal Price(string size)
        {
            return size == "Large" ? 12.5m : 9m;
        }
    }
}
