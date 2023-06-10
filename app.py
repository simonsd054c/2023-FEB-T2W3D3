from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow
from marshmallow import fields
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from sqlalchemy.exc import IntegrityError
from datetime import timedelta

app = Flask(__name__)
# connect to the database                  dbms      adapter   db_user password  url      port  db_name
app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql+psycopg2://feb_dev:123456@localhost:5432/feb_ecommerce"
app.config["JWT_SECRET_KEY"] = "secret"

db = SQLAlchemy(app)
ma = Marshmallow(app)

bcrypt = Bcrypt(app)
jwt = JWTManager(app)

# Model - User
class User(db.Model):
    # table name
    __tablename__ = "users"
    # attributes
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100), nullable=False, unique=True)
    password = db.Column(db.String(100), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    products = db.relationship('Product', back_populates='user', cascade='all, delete')

# Model - Product
class Product(db.Model):
    # define tablename
    __tablename__ = "products"
    # define the primary key
    id = db.Column(db.Integer, primary_key=True)
    # more attributes
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(100))
    price = db.Column(db.Float)
    stock = db.Column(db.Integer)

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    user = db.relationship('User', back_populates='products')

class UserSchema(ma.Schema):
    products = fields.List(fields.Nested('ProductSchema', exclude=['user']))

    class Meta:
        fields = ("id", "name", "email", "password", "is_admin", "products")

users_schema = UserSchema(many=True, exclude=['password'])
user_schema = UserSchema(exclude=['password'])

class ProductSchema(ma.Schema):
    user = fields.Nested('UserSchema', only=['email', 'name'])

    class Meta:
        # fields
        fields = ("id", "name", "description", "price", "stock", "user")

# to handle more than one product data
products_schema = ProductSchema(many=True)
# to handle a single product data
product_schema = ProductSchema()

# CLI Commands
@app.cli.command("create")
def create_db():
    db.create_all()
    print("Tables created")

@app.cli.command("seed")
def seed_db():
    # users list
    users = [
        User(
            name="admin",
            email="admin@admin.com",
            password=bcrypt.generate_password_hash("admin123").decode('utf-8'),
            is_admin=True
        ),
        User(
            name="user1",
            email="user1@mail.com",
            password=bcrypt.generate_password_hash("user123").decode('utf-8')
        )
    ]
    # add the users list to session
    db.session.add_all(users)
    db.session.commit()
    # create a product instance / object
    product1 = Product(
        name="Product 1",
        description="Product 1 desc",
        price=4.75,
        stock=20,
        user_id=users[0].id
    )
    product2 = Product()
    product2.name = "Product 2"
    # product2.description = "Product 2 desc"
    product2.price = 159.99
    product2.stock = 150
    product2.user = users[1]
    # add this to db session
    db.session.add(product1)
    db.session.add(product2)
    # commit
    db.session.commit()
    print("Tables seeded")

@app.cli.command("drop")
def drop_db():
    db.drop_all()
    print("Tables dropped")


@app.route("/")
def hello_word():
    return "<h1>Hello Hello World World</h1>"

@app.route("/another_route")
def another_route():
    return "This is another route, not the same as previous"

@app.route("/products")
def get_products():
    # products_list = Product.query.all() # SELECT * FROM products;
    stmt = db.select(Product) # SELECT * FROM products; [(1), (2), (3), (4)]
    products_list = db.session.scalars(stmt) # [1, 2, 3, 4]
    data = products_schema.dump(products_list) # JSON serializable object
    return data

@app.route("/products", methods=["POST"])
@jwt_required()
def create_product():
    product_fields = product_schema.load(request.get_json())
    new_product = Product(
        name=product_fields.get("name"),
        description=product_fields.get("description"),
        price=product_fields.get("price"),
        stock=product_fields.get("stock"),
        user_id=get_jwt_identity()
    )
    db.session.add(new_product)
    db.session.commit()
    return product_schema.dump(new_product), 201


@app.route("/products/<int:id>", methods=["PUT", "PATCH"])
@jwt_required()
def update_product(id):
    # find the product from the db to update
    stmt = db.select(Product).filter_by(id=id)
    product = db.session.scalar(stmt)
    # the data to be updated - received from body of put or patch request
    body_data = request.get_json()
    # updating the attributes
    if product:
        # the product's owner(product's user_id) doesn't match with the user
        # trying to edit
        if str(product.user_id) != get_jwt_identity():
            return {"error": "Not authorised to edit the product"}, 403
        product.name = body_data.get('name') or product.name
        product.description = body_data.get('description') or product.description
        product.price = body_data.get('price') or product.price
        product.stock = body_data.get('stock') or product.stock
        # commit
        db.session.commit()
        return product_schema.dump(product)
    else:
        return jsonify(message=f"Product with id {id} doesn't exist"), 404


@app.route("/products/<int:id>", methods=["DELETE"])
@jwt_required()
def delete_product(id):
    is_admin = authorise_as_admin()
    if not is_admin:
        return {"error": "User other than admin not authorised to delete"}, 403
    stmt = db.select(Product).where(Product.id==id)
    product = db.session.scalar(stmt)
    if product:
        db.session.delete(product)
        db.session.commit()
        return jsonify(message=f"Product {product.name} deleted successfully")
    else:
        return jsonify(message=f"Product with id {id} doesn't exist"), 404


@app.route("/products/<int:id>")
def get_product(id):
    # product = Product.query.get(id) # SELECT * FROM products WHERE id=id(paramter)
    # product = db.session.get(Product, id)
    # OR to keep it consistent across all routes
    stmt = db.select(Product).filter_by(id=id)
    product = db.session.scalar(stmt)
    if(product):
        data = product_schema.dump(product)
        return data
    else:
        return jsonify(message="Product with that id doesn't exist"), 404

@app.route("/auth/register", methods=["POST"])
def register_user():
    try:
        # get the body data
        body_data = request.get_json()
        password = body_data.get("password")
        # create user instance
        user = User(
            email=body_data.get("email"),
            name=body_data.get("name"),
            # this generates in bytes format and we decode that to utf-8 format
            password=bcrypt.generate_password_hash(password).decode('utf-8')
        )
        # add user to session
        db.session.add(user)
        # commit
        db.session.commit()
        return user_schema.dump(user), 201
    except IntegrityError:
        return jsonify(error="Email already exists"), 409
    
@app.route("/auth/login", methods=["POST"])
def login_user():
    body_data = request.get_json()
    # find user by email
    stmt = db.select(User).filter_by(email=body_data.get("email"))
    user = db.session.scalar(stmt)
    # if user exists and password match
    if user and bcrypt.check_password_hash(user.password, body_data.get("password")):
        # return a jwt token
        token = create_access_token(identity=str(user.id), expires_delta=timedelta(days=1))
        return {"email": user.email, "token": token, "is_admin": user.is_admin}
    else:
        return {"error": "Invalid email or password"}, 401

def authorise_as_admin():
    user_id = get_jwt_identity()
    stmt = db.select(User).filter_by(id=user_id)
    user = db.session.scalar(stmt)
    return user.is_admin